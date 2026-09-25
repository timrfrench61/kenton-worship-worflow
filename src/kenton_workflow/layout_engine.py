"""Template-preserving, explainable bulletin rules. No independent PDF layout."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

from lxml import etree
from kenton_workflow.sync import checked_path

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NS = {'w': W[1:-1]}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(node):
    pieces = []
    for item in node.iter():
        if item.tag == W+'t': pieces.append(item.text or '')
        elif item.tag in (W+'br', W+'tab'): pieces.append(' ')
    return ''.join(pieces).strip()


def replace_text(node, old, new):
    """Replace one contiguous text span without flattening the paragraph's runs."""
    nodes = node.findall('.//'+W+'t')
    joined = ''.join(n.text or '' for n in nodes)
    if not old or joined.count(old) != 1:
        raise ValueError('Text slot must match exactly once in its mapped paragraph.')
    start, end = joined.index(old), joined.index(old)+len(old)
    offset = 0
    inserted = False
    for n in nodes:
        original = n.text or ''
        left, right = max(start-offset, 0), min(end-offset, len(original))
        if left < right:
            n.text = original[:left] + (new if not inserted else '') + original[right:]
            n.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            inserted = True
        offset += len(original)


def prop(paragraph, name, attributes=None):
    ppr = paragraph.find(W+'pPr')
    if ppr is None:
        ppr = etree.Element(W+'pPr'); paragraph.insert(0, ppr)
    element = ppr.find(W+name)
    if element is None: element = etree.SubElement(ppr, W+name)
    for key, value in (attributes or {}).items(): element.set(W+key, str(value))
    order = ['pStyle','keepNext','keepLines','pageBreakBefore','framePr','widowControl','numPr',
             'suppressLineNumbers','pBdr','shd','tabs','suppressAutoHyphens','kinsoku','wordWrap',
             'overflowPunct','topLinePunct','autoSpaceDE','autoSpaceDN','bidi','adjustRightInd',
             'snapToGrid','spacing','ind','contextualSpacing','mirrorIndents','suppressOverlap',
             'jc','textDirection','textAlignment','textboxTightWrap','outlineLvl','divId',
             'cnfStyle','rPr','sectPr','pPrChange']
    for child in sorted(list(ppr),key=lambda e: order.index(e.tag[len(W):]) if e.tag[len(W):] in order else len(order)):
        ppr.append(child)
    return element


def publish_new(path, payload):
    path = checked_path(Path(path))
    if path.exists(): raise ValueError(f'Output already exists: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name); stream.write(payload)
        os.link(temporary, path)
    finally:
        if temporary: temporary.unlink(missing_ok=True)


def build(content_path, template_path, profile_path, output_path):
    paths = [Path(content_path), Path(template_path), Path(profile_path)]
    fingerprints = [sha(p) for p in paths]
    content = json.loads(paths[0].read_text(encoding='utf-8-sig'))
    profile = json.loads(paths[2].read_text(encoding='utf-8-sig'))
    if profile.get('template_sha256') != fingerprints[1]:
        raise ValueError('Template differs from the mapped reference; remap explicitly.')
    spacing = profile['spacing']
    within, between, ceiling = (spacing[k] for k in ('within_pt', 'between_pt', 'maximum_pt'))
    if not (0 <= within <= 6 and within < between <= ceiling <= 18):
        raise ValueError('Spacing must be 0–6 pt within groups and at most 18 pt between groups.')
    fixes = []
    with ZipFile(paths[1]) as original:
        names = original.namelist()
        document = etree.fromstring(original.read('word/document.xml'))
        body = document.find(W+'body')
        paragraphs = body.findall(W+'p')
        tables = body.findall(W+'tbl')
        sections_before = [etree.tostring(s) for s in document.findall('.//'+W+'sectPr')]
        if len(paragraphs) != profile['paragraph_count']:
            raise ValueError('Paragraph count differs from template profile.')
        for slot in profile['slots']:
            if slot['field'] not in content or not isinstance(content[slot['field']], str):
                raise ValueError(f"Missing string field: {slot['field']}")
            if not content[slot['field']].strip() and not slot.get('allow_empty'):
                raise ValueError(f"Empty required field: {slot['field']}")
            replace_text(paragraphs[slot['paragraph']], slot['old'], content[slot['field']])
            fixes.append({'rule': 'fill_named_slot', 'field': slot['field'], 'paragraph': slot['paragraph']})
        responsive = profile.get('responsive')
        if responsive:
            lines = content.get('responsive_lines')
            if not isinstance(lines, list) or not lines:
                raise ValueError('Responsive Scripture lines are required.')
            if content.get('translation') != profile['translation']:
                raise ValueError('Translation differs from the explicitly configured translation.')
            if content.get('responsive_reference') != content.get('call_reference'):
                raise ValueError('Responsive text reference differs from planned reference.')
            table = tables[responsive['table']]
            rows = table.findall(W+'tr')
            new_rows = []
            for line in lines:
                if line.get('speaker') not in responsive['speaker_rows'] or not isinstance(line.get('text'), str) or not line['text'].strip():
                    raise ValueError('Every responsive line requires a supported speaker and text.')
                row = deepcopy(rows[responsive['speaker_rows'][line['speaker']]])
                cells = row.findall(W+'tc')
                for cell, value in zip(cells, (line['speaker'], line['text'])):
                    ps = cell.findall(W+'p')
                    if len(ps) != 1: raise ValueError('Responsive cell structure requires explicit mapping.')
                    old = ''.join(ps[0].xpath('.//w:t/text()', namespaces=NS))
                    replace_text(ps[0], old, value)
                    prop(ps[0], 'keepLines'); prop(ps[0], 'widowControl')
                trpr = row.find(W+'trPr')
                if trpr is None: trpr = etree.Element(W+'trPr'); row.insert(0,trpr)
                etree.SubElement(trpr,W+'cantSplit')
                new_rows.append(row)
            for row in rows: table.remove(row)
            for row in new_rows: table.append(row)
            fixes.append({'rule': 'responsive_rows_preserve_table_style', 'rows': len(new_rows)})
        for index in profile.get('remove_empty_paragraphs', []):
            p = paragraphs[index]
            if text(p) or p.xpath('.//w:drawing|.//w:pict|.//w:br|.//w:fldChar',namespaces=NS):
                raise ValueError(f'Refusing to remove nonempty or structural paragraph {index}.')
            body.remove(p)
            fixes.append({'rule':'remove_mapped_empty_scaffolding','paragraph':index})
        for index in profile.get('remove_leading_page_break', []):
            p=paragraphs[index]
            if any(text(n) for n in body.iterchildren() if n is not p and list(body).index(n)<list(body).index(p)):
                raise ValueError('Only a leading blank-page break can be removed automatically.')
            for br in p.xpath('.//w:br[@w:type="page"]|.//w:lastRenderedPageBreak',namespaces=NS):
                br.getparent().remove(br)
            fixes.append({'rule':'remove_confirmed_leading_blank_page','paragraph':index})
        rendered_groups = []
        used = set()
        for group in profile['groups']:
            indices = group['paragraphs']
            if not indices or any(i in used for i in indices): raise ValueError('Groups must be nonempty and disjoint.')
            used.update(indices)
            members=[paragraphs[i] for i in indices if paragraphs[i].getparent() is body]
            for i,p in enumerate(members):
                prop(p,'keepLines'); prop(p,'widowControl')
                prop(p,'keepNext',{'val':1 if i<len(members)-1 else 0})
                if i and p.xpath('.//w:br[@w:type="page"]',namespaces=NS):
                    raise ValueError(f"Group {group['id']} crosses an explicit page break.")
                gap=prop(p,'spacing',{'before':round((between if i==0 else 0)*20), 'after':round(within*20)})
                # Preserve line spacing; disable inherited automatic paragraph spacing only.
                gap.set(W+'beforeAutospacing','0'); gap.set(W+'afterAutospacing','0')
            rendered_groups.append({'id':group['id'], 'paragraphs':[text(p) for p in members if text(p)],
                                    'keep_together':True})
            fixes.append({'rule':'bounded_group_spacing_and_keep','group':group['id']})
        # The call heading and every responsive row are one non-splitting chain.
        if responsive:
            heading=paragraphs[responsive['heading_paragraph']]
            prop(heading,'keepNext',{'val':1})
            row_paragraphs=tables[responsive['table']].findall('.//'+W+'p')
            for i,p in enumerate(row_paragraphs):
                prop(p,'keepNext',{'val':1 if i<len(row_paragraphs)-1 else 0})
            rendered_groups.append({'id':'responsive-reading','paragraphs':[text(heading)]+[
                line['speaker']+' '+line['text'] for line in content['responsive_lines']], 'keep_together':True})
        if sections_before != [etree.tostring(s) for s in document.findall('.//'+W+'sectPr')]:
            raise ValueError('Page geometry changed unexpectedly.')
        result=BytesIO()
        with ZipFile(result,'w') as target:
            for info in original.infolist():
                target.writestr(deepcopy(info), etree.tostring(document,xml_declaration=True,encoding='UTF-8',standalone=True)
                    if info.filename=='word/document.xml' else original.read(info.filename))
        with ZipFile(BytesIO(result.getvalue())) as verify:
            changed=[name for name in names if verify.read(name)!=original.read(name)]
            if any(name!='word/document.xml' for name in changed): raise ValueError('Preserved package part changed.')
        sections=[]
        for s in document.findall('.//'+W+'sectPr'):
            size,margin=s.find(W+'pgSz'),s.find(W+'pgMar')
            sections.append({'width':int(size.get(W+'w'))/20,'height':int(size.get(W+'h'))/20,
                             'margins':{k:int(margin.get(W+k))/20 for k in ('top','bottom','left','right')}})
    if fingerprints != [sha(p) for p in paths]: raise ValueError('Input changed during build; retry after saving.')
    output=checked_path(Path(output_path))
    if output.suffix.lower()!='.docx' or checked_path(Path.cwd()/'work') not in output.parents:
        raise ValueError('Output must be a DOCX under this repository work/ folder.')
    report_path=output.with_suffix('.layout.json')
    if output.exists() or report_path.exists(): raise ValueError('Use a new output name; existing output/report is preserved.')
    report={'status':'render_required','docx':str(output),'docx_sha256':hashlib.sha256(result.getvalue()).hexdigest(),
            'inputs':[{'path':str(p),'sha256':h} for p,h in zip(paths,fingerprints)],
            'changed_parts':changed,'rules_applied':fixes,'groups':rendered_groups,'sections':sections,
            'required_text':profile.get('required_fields',[]),
            'field_values':{key:content[key] for key in profile.get('required_fields',[])},
            'expected_pages':profile.get('expected_pages'),'maximum_group_gap_pt':ceiling,
            'limitations':['Native Word export and rendered checks have not run.','Human visual and content approval required.']}
    publish_new(output,result.getvalue())
    publish_new(report_path,(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))
    return report
