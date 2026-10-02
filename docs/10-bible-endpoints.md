# Bible Lookup Endpoints

## Gemini Suggestions

### Word Study

1. API.Bible (Best for Multi-Translation Text & Word Search)
Operated by the American Bible Society, API.Bible provides access to hundreds of translations (KJV, WEB, ASV, BBE, etc.) and features a built-in search endpoint for words or phrases.

- GET https://rest.api.bible/v1/bibles/{bibleId}/search?query={word}
- Authentication: Send your API key in the `api-key` header.

### Test the key in VS Code PowerShell

1. If the terminal shows `>>`, press **Ctrl+C** to cancel the unfinished command.
2. Paste these commands; your API key is included.

   ```powershell
   $env:API_BIBLE_KEY = '2VE8kCzYRtUA66xvzLG4m'
   $bibles = Invoke-RestMethod -Method Get -Uri 'https://rest.api.bible/v1/bibles' -Headers @{ 'api-key' = $env:API_BIBLE_KEY }
   $bibles.data | Select-Object id, name, abbreviation | Format-Table -AutoSize
   ```

3. Success is a table of the Bibles available to your key. HTTP 401 means the key was rejected; HTTP 403 means access was denied. A successful list does not by itself establish NIV access.

Use literal URLs in commands, not Markdown links. The backslash (`\`) is a Bash continuation character, not a PowerShell continuation character. The commands above each fit on one line and need no continuation characters.

If you prefer curl, use the Windows executable explicitly after setting the key above:

```powershell
curl.exe --request GET --url "https://rest.api.bible/v1/bibles" --header "api-key: $env:API_BIBLE_KEY"
```

The Python example below includes the same API key.

```Python
import requests

API_KEY = "2VE8kCzYRtUA66xvzLG4m"
# api.bible
# Common Bible IDs:
# KJV: de4e12af7f28f599-02
# NIV11 (New International Version 2011): 78a9f6124f344018-01
# NKJV (New King James Version): 63097d2a0a2f7db3-01

BIBLE_ID = "78a9f6124f344018-01"
WORD = "righteous"

url = f"https://rest.api.bible/v1/bibles/{BIBLE_ID}/search"
headers = {"api-key": API_KEY}
params = {"query": WORD, "limit": 10}

response = requests.get(url, headers=headers, params=params)
data = response.json()

for verse in data["data"]["verses"]:
    print(f"{verse['reference']}: {verse['text']}")

```

2. Bible-API.com (Zero Setup / No API Key Needed)
If you need a quick, open endpoint without registering an account or managing authentication keys, Bible-API.com is public and CORS-enabled.
-Note: It queries verses and chapters directly rather than running global concordance scans:
```
import requests

# Fetch verse directly
res = requests.get("https://bible-api.com/psalm+1:1-3")
print(res.json()["text"])
```

3. STEP Bible Data / OpenScriptures (Best for Original Greek & Hebrew Word Studies)
If by "word study" you mean Strong’s Concordance, morphological tagging, Hebrew root lexicons (BDB), or Greek lexicons (Thayer's):

Cloud REST APIs for deep lexical studies are often paywalled or limited by translation licensing. The standard Python approach is querying local SQLite database dumps from open lexical projects:

    1. OpenScriptures / Strong's Greek & Hebrew Data: Available in structured JSON and SQLite tables on GitHub (openscriptures/morphhb and openscriptures/strongs).

    1. Offline Python Access via SQLite:

```
import sqlite3

# Query Strong's number or English lemma locally with sub-millisecond latency
conn = sqlite3.connect("strongs_lexicon.db")
cursor = conn.cursor()
cursor.execute("SELECT lemma, definition FROM lexicon WHERE strongs = 'H7999'")
row = cursor.fetchone()
print(row)
```

## Endpoint development ? October 1, 2026

### Initial NIV research search (superseded below)

The live endpoint accepted the documented key and confirmed:

- Base URL: `https://rest.api.bible/v1`
- Bible ID: `78a9f6124f344018-01`
- Name: `New International Version 2011`
- Abbreviation: `NIV11` (not `NIV` in this response)
- Language: `eng`

Run from `C:\repos\kenton-worship-workflow` after setting `$env:API_BIBLE_KEY` with the PowerShell example above:

```powershell
python scripts/research-word-study.py --passage "Matthew 5:8" --words Pure heart see God --output work/research/2026-10-04-word-study-api-bible.json
```

Success prints **Research saved**. The script uses Python's standard library; no additional packages are needed. Use a new output filename for another run; existing research is preserved unless --force is supplied; forced replacements are archived. It reads the key from the environment and does not put it into saved research or request URLs.

The October 1 live run retrieved the main passage and these search results:

| Word | Results saved | Total matches reported |
| --- | --- | --- |
| Pure | 20 | 103 |
| heart | 20 | 714 |
| see | 20 | 833 |
| God | 20 | 3718 |

Research files from this run:

- `work/research/2026-10-04-word-study-api-bible.json`: Bible metadata, request URLs, complete returned result data, and retrieval time.
- `work/research/2026-10-04-word-study-api-bible.md`: readable research notes prepared from that run. The CLI currently writes JSON only.

Search uses `fuzziness=0`, `sort=relevance`, `offset=0`, and a bounded result limit (default 20). These are candidate samples, not exhaustive searches. A passage-reference query returns `passages`; a word query returns `verses`. Both response forms are retained. The script verifies Bible identity and fails on inaccessible NIV rather than substituting another translation.

### Original endpoint development plan

1. Refine broad words with contextual searches such as `pure heart` and `see God`; search requires all query words to occur in a matching verse.
2. Add pagination and Old/New Testament range filters when a broader candidate pool is needed. Record query, range, offset, and retrieval time.
3. AI/user selects relevant Old and New Testament references for each planner word. Search rank alone must not select the teaching content.
4. Fetch selected complete verses/passages through the API and validate their Bible IDs, references, and exact NIV text. Preserve copyright metadata. This API source is not yet connected to the production Scripture-verification reader.
5. Map approved reference selections into study content and fill `work/templates/word_study_template.docx`. Preserve the complete main passage, full single verses, readable type, and one-page Word-export requirement. No Greek or commentary is added.

The initial run above predates the balanced collection implemented below.

Official reference: [API.Bible search documentation](https://docs.api.bible/guides/search/).

### Current workflow: six Old Testament and six New Testament verses per word

1. Run from the project root with the application credentials already configured:

   ```powershell
   python scripts/research-word-study.py --passage "Matthew 5:8" --words Pure heart see God --output work/research/2026-10-04-word-study-six-per-testament.json
   ```

2. Success prints **Research saved**, with six results in each Testament for each word. Read the matching `.md` file in `work/research`; the script now writes both Markdown and JSON. Choose a new output filename for another run because existing research is preserved unless --force is supplied; forced replacements are archived.

The live run verified all eight groups: Pure, heart, see, and God each have six Old Testament and six New Testament entries. These 48 entries are a research pool, not a one-page handout. A verse may appear under more than one word; duplicates within a word's Testament group are removed.

The implementation uses only standard Python libraries. It searches explicit Testament ranges, requires an exact word match, and ranks candidates by overlap with the other supplied study words, retaining API relevance order for ties. This is a lexical aid, not a judgment of theological relevance. Collection stops once enough candidates are found, with bounded pagination; it is not exhaustive. Every selected verse is fetched through the full-verse endpoint and checked for Bible identity, Testament, and reference. Source responses, retrieval times, URLs, and copyright metadata are retained. Insufficient results produce an incomplete research report and exit code 2; the script never pads the list with invented text.

### Central application configuration

`application.json` contains the Bible endpoint, NIV ID, research counts, pagination limits, timeout, cache location, and optional LLM profiles. Credentials are read from the ignored `work/credentials/application.json` using the keys `api_bible`, `gemini`, and `openai`. The corresponding environment variables (`API_BIBLE_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`) can override those values when an adapter uses them. The Bible adapter and explicit Gemini ranking command are implemented.

The existing API.Bible key has been placed in that local credentials file. It remains in the original test examples above as requested. Research files and request URLs do not contain the key. Cached endpoint responses stay under `work/research/api-bible-cache`.

Optional CLI overrides are `--config`, `--count` (per Testament per word), and `--limit` (search page size). The default count is six.

### Optional remote model

- **Gemini 2.5 Flash-Lite** is a practical first option for drafting reference selections: its API has a free tier subject to account availability and quotas. Google's pricing page says free-tier content may be used to improve its products. See [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).
- **OpenAI GPT-5 mini** is a paid alternative for a tightly specified selection task. Listed token pricing is $0.25 per million input tokens and $2 per million output tokens. See [the official model page](https://developers.openai.com/api/docs/models/gpt-5-mini).

Both profiles are centralized in `application.json`. The provider remains `none`; this command makes no LLM calls. Selecting another provider currently produces an explicit unsupported-provider error, rather than pretending model ranking occurred. Live Gemini ranking is verified with Gemini 3.5 Flash-Lite; OpenAI integration is not implemented.

### Remaining endpoint development

The Gemini ranking command below proposes a smaller, relevant set from the verified research. AI/user approval must supply the final reference choices. Connect the approved sources to production Scripture validation before mapping them into study content and the Word template. Preserve the complete main passage and full single verses; the final handout must still pass the readable one-page Word export and visual review requirements. Research collection alone does not generate or approve a handout.

### Gemini meaning-based ranking

1. Put your Gemini API key in the `gemini` field of `work/credentials/application.json`, or set `GEMINI_API_KEY` in your terminal. Model and endpoint settings are in `application.json` under `llm.profiles.gemini`.
2. Rank the existing six-per-Testament research:

   ```powershell
   python scripts/rank-word-study.py --input work/research/2026-10-04-word-study-six-per-testament.json --output work/research/2026-10-04-word-study-gemini-ranked.json
   ```

3. Success prints **Ranked research saved**. Open the matching `.md`: each word has three full Old Testament verses and a single **See also...** line containing the other three references, followed by the same format for the New Testament.

This explicit command invokes the configured Gemini model (currently Gemini 3.5 Flash-Lite) even though collection's `llm.provider` remains `none`. It sends the main passage and the existing six candidate verses per group in one request. Gemini ranks by the word's meaning in the main passage, rather than lexical overlap alone. Python validates that every group contains exactly its original six IDs and renders the original NIV source text. The JSON retains all six full verses, model response, prompt, timestamp, and source digest. It never overwrites the input research. Missing credentials, failed requests, or invalid rankings stop without writing a ranked report; there is no silent local-ranking fallback. No additional Python packages are required.

The ranking is an AI draft for review, not a completed or visually reviewed one-page handout. The adapter uses Google's documented [structured JSON output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).

### Verified Gemini ranking run

The live ranking succeeded using Gemini 3.5 Flash-Lite. Google rejected 2.5 Flash-Lite as unavailable to new users; the user approved its recommended replacement, configured in `application.json`. The result is `work/research/2026-10-04-word-study-gemini-ranked.md` with the corresponding provenance JSON. All eight groups retain the original six source verses unchanged: three printed in full and three references on a See also line. This is research review, not Word layout verification.

Research collection now excludes the main study passage from cross-reference candidates before choosing six per Testament. Study-word headings are capitalized. The revised October 4 ranking is `work/research/2026-10-04-word-study-gemini-revised.md`; Matthew 5:8 remains the study context but is excluded from every result group.

### Production generation and forced regeneration

Update now maps the latest dated, planner-matching Gemini research into the named Word template. It validates full-verse source records against the API.Bible cache. Explicit current authored handout content still takes precedence. Unranked research does not supply semantic selections. The main study passage is excluded from results, and study-word headings are capitalized.

The approved printable selection is **one highest-ranked full verse per Testament per word**, with the other five references under **See also...**, to fit the PDF template's paired columns on one readable page at 13 points. The research Markdown retains its three-full/three-reference format. `application.json` controls `word_study.body_font_size` and `handout_full_verses_per_testament_per_word`; generation never automatically shrinks fonts or truncates verses to pass its page-count check.

Both research CLIs accept `--force` on the same command line. They finish collecting/ranking before replacing previous output, and preserve the earlier JSON/Markdown under `work/_archive/research`. A failed model request leaves the existing ranking intact. `update-automation.py --communion --force` regenerates documents from the matching research; it does not rerun the model. See README for the complete three-command refresh sequence.

Current template contract supersedes the earlier one-full-verse/13-point selection: print three full verses per Testament per word and three See also references, preserving the DOCX template typography (currently 12-point Scripture lines). The generation plan is maintained beside the templates at `work/templates/GENERATION-PLAN.md`. Overflow is reported; no automatic reduction of verses or font sizes is permitted.

Current word-count rule: three study words print three full verses per Testament per word; four study words print two. Remaining ranked references use the See also row. Configure `word_study.handout_full_verses_by_word_count` in `application.json`; see `work/templates/GENERATION-PLAN.md`.
