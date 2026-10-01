# Official Ryde policy text

Word-for-word copies of Ryde's published policies, fetched by
`scripts/fetch_official_policies.py`. The only changes are removing HTML and
turning each article or clause title into a `## ` heading so the indexer keeps
one article per chunk. Nothing is paraphrased or summarised.

| Files | Source | What is kept |
|---|---|---|
| `ryde_help_<category>_<section>.md` | Ryde Help Centre, help.rydesharing.com (public Help Center API) | Dispute-related articles only: fees, waivers, fares, ERP, routes, mess and cleaning, ratings, conduct, safety, accidents, lost items, RydeSEND claims. Each article shows its URL and official last-updated date. Articles the Help Centre repeats in two sections are kept once (newest copy). |
| `ryde_site_*.md` | rydesharing.com | Terms of Use, Code of Conduct, Privacy Policy, Safe Driving Tips, Keeping Platform Work Safe and Fair |

Every file states the date it was fetched. To refresh:

```
python scripts/fetch_official_policies.py
```

Rider and driver articles can state different amounts for the same fee (for
example the rider pays a S$6.61 cancellation fee, the driver receives S$4.50).
Both are kept as published; cite the one that matches who filed the dispute.

## Section tags (`policy_tags.json`)

Every section (the text under each `## ` heading, plus "Overview") has metadata the indexer stores on its
chunks: `dispute_types` (the 8 classifier types, `general` for any dispute, `none` for text that cannot
help a ruling) and `audience` (`rider`, `driver`, `both`). Each tag also becomes a boolean flag
(`dt_no_show`, ...) for filtering. Tags were proposed by a model, reviewed by hand (`reviewed: true` marks
the edited ones), and checked against the eval answer keys: every expected section carries its case's type.
After editing a heading or a tag, re-index (`python scripts/index_policies.py --clear`).
`tests/test_policy_tags.py` fails if a heading has no tag.
