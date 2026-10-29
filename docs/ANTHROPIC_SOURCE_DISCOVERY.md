# Anthropic personal-blog source discovery

Checked 2026-10-28. This is a supported initial registration, not a complete employee census. Public LinkedIn searches were used for discovery; no LinkedIn session, bulk employee scraping, cookies or contact database was used. Author-owned pages supply affiliation and blog ownership evidence.

## Registered

| Author | Identity evidence | Blog | Collection check |
| --- | --- | --- | --- |
| Felix Rieseberg | https://felixrieseberg.com/about-me/ | https://felixrieseberg.com/ | `/rss/`: HTTP 200, RSS root, 15 items |
| Jack Clark | https://jack-clark.net/about/ | https://jack-clark.net/ | `/feed/`: HTTP 200, RSS root, 10 items |
| Chris Olah | https://colah.github.io/about.html | https://colah.github.io/ | `/rss.xml`: HTTP 200, RSS root, 6 items; historical archive, not claimed recently active |
| Amanda Askell | https://askell.io/ links her blog and describes Anthropic role | https://askell.blog/ | `/rss/`: HTTP 200, RSS root, 15 items |
| Dario Amodei | https://darioamodei.com/ | same | Homepage HTTP 200; `/rss.xml` and `/feed` HTTP 404. Registered disabled until HTML adapter exists |
| Jan Leike | https://jan.leike.name/ explicitly links his blog and current Anthropic work | https://aligned.substack.com/ | `/feed` returned HTML rather than RSS in this environment. Registered disabled, not falsely marked ready |

## Excluded or unresolved candidates

- Nelson Elhage: https://nelhage.com/ lists Anthropic under *previous* work. Blog/feed are valid (`https://blog.nelhage.com/atom.xml`, 98 items), but excluded from the current-employee pack. Can form a separate alumni pack later.
- Samuel Marks: public LinkedIn result https://www.linkedin.com/in/samuel-marks-3211b134a identifies Anthropic. `samuelmarks.com` is a coming-soon site and does not establish author identity. A Harvard personal page is a candidate, but blog/update transport is not yet established. Not subscribed.
- `amandaaskell.com` was inaccessible. The author-owned `askell.io` supplies the actual blog link. No similarly named third-party/fan site used.
- Neel Nanda: blog found; current Anthropic employment not established, so excluded.
- Official Alignment Science blog is a valid separate organizational source, not a personal blog; not silently added to this pack.

## Extend the registry

Continue public LinkedIn company/person discovery with a persistent coverage ledger (query, candidate, identity evidence, personal website, feed, validation result, checked_at). Verify current employment separately from paper authorship. Resolve aliases and duplicate sites. Probe discovered feed links before conventional paths. Keep denied/unavailable transports visible. Publish new pack versions for explicit adoption; discovery never mutates an existing user's subscription.
