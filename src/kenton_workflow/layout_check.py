"""Checks exported Word PDF geometry; never claims human approval."""
import json
from pathlib import Path
import re
import unicodedata

from kenton_workflow.layout_engine import sha


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC',value).replace('\u00ad','').split())


def check(report_path, pdf_path, proof_path):
    import pdfplumber
    report=json.loads(Path(report_path).read_text(encoding='utf-8-sig'))
    proof=json.loads(Path(proof_path).read_text(encoding='utf-8-sig'))
    issues=[]
    if proof.get('renderer')!='Microsoft Word' or proof.get('docx_sha256')!=report['docx_sha256']:
        raise ValueError('Native Word export proof does not match this generated DOCX.')
    if sha(report['docx'])!=report['docx_sha256'] or sha(pdf_path)!=proof.get('pdf_sha256'):
        raise ValueError('DOCX or PDF changed after export; regenerate verification.')
    if len(report['sections'])!=1:
        raise ValueError('This PDF checker requires a single-section template profile.')
    geometry=report['sections'][0]
    all_pages=[]
    with pdfplumber.open(pdf_path) as pdf:
        if report.get('expected_pages') is not None and len(pdf.pages)!=report['expected_pages']:
            issues.append(f"Expected {report['expected_pages']} pages; exported {len(pdf.pages)}. Review overflow, not smaller fonts.")
        for number,page in enumerate(pdf.pages,1):
            words=page.extract_words(x_tolerance=2,y_tolerance=3)
            if not words: issues.append(f'Page {number} is blank.')
            if abs(page.width-geometry['width'])>1 or abs(page.height-geometry['height'])>1:
                issues.append(f'Page {number} dimensions differ from template.')
            margin=geometry['margins']; tolerance=3
            bad=[w for w in words if w['x0']<margin['left']-tolerance or w['x1']>page.width-margin['right']+tolerance
                 or w['top']<margin['top']-tolerance or w['bottom']>page.height-margin['bottom']+tolerance]
            if bad: issues.append(f'Page {number}: {len(bad)} text fragments outside template text margins; inspect before approval.')
            words=[{**w,'text':normalize(w['text'])} for w in words]
            all_pages.append(words)
    def locate(phrase):
        tokens=normalize(phrase).split(); found=[]
        for number,words in enumerate(all_pages,1):
            values=[w['text'] for w in words]
            for i in range(len(values)-len(tokens)+1):
                if values[i:i+len(tokens)]==tokens:
                    selected=words[i:i+len(tokens)]
                    found.append({'page':number,'top':min(w['top'] for w in selected),'bottom':max(w['bottom'] for w in selected)})
        return found
    checks=[]
    for group in report['groups']:
        locations=[]
        for paragraph in group['paragraphs']:
            matches=locate(paragraph)
            if len(matches)!=1:
                issues.append(f"Group {group['id']}: expected one rendered match for mapped paragraph, found {len(matches)}.")
            else: locations.append(matches[0])
        if len({p['page'] for p in locations})>1:
            issues.append(f"Group {group['id']} is split across pages.")
        for first,second in zip(locations,locations[1:]):
            if first['page']==second['page'] and second['top']-first['bottom']>report['maximum_group_gap_pt']+3:
                issues.append(f"Group {group['id']} has an excessive internal gap ({second['top']-first['bottom']:.1f} pt).")
        checks.append({'group':group['id'],'locations':locations})
    full=normalize(' '.join(w['text'] for words in all_pages for w in words))
    # Merge nested/overlapping groups (for example the responsive heading and table)
    # before checking gaps between distinct sections on the same page.
    for page_number in range(1,len(all_pages)+1):
        spans=[]
        for group in checks:
            positions=[p for p in group['locations'] if p['page']==page_number]
            if positions: spans.append((min(p['top'] for p in positions),max(p['bottom'] for p in positions)))
        merged=[]
        for top,bottom in sorted(spans):
            if merged and top<=merged[-1][1]: merged[-1]=(merged[-1][0],max(bottom,merged[-1][1]))
            else: merged.append((top,bottom))
        for first,second in zip(merged,merged[1:]):
            gap=second[0]-first[1]
            if gap>report['maximum_group_gap_pt']+6:
                issues.append(f'Page {page_number}: excessive gap between mapped sections ({gap:.1f} pt).')
    for field,value in report['field_values'].items():
        if normalize(value) not in full: issues.append(f'Required content missing from PDF: {field}')
    result={'status':'layout_check_failed' if issues else 'visual_review_required',
            'issues':issues,'checks':checks,'pdf_sha256':sha(pdf_path),'docx_sha256':report['docx_sha256'],
            'pages':len(all_pages),'human_approved':False}
    destination=Path(pdf_path).with_suffix('.checks.json')
    destination.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
