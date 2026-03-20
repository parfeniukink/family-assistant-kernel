# Inference Pricing

OpenAI model cost estimation for the news pipeline.

## Model Pricing (as of March 2026)

| Model        | Input ($/1M tokens) | Output ($/1M tokens) |
| ------------ | ------------------- | -------------------- |
| gpt-4.1-mini | $0.40               | $1.60                |
| gpt-4.1      | $2.00               | $8.00                |
| o4-mini      | $1.10               | $4.40                |

## Agent → Model Mapping

| Agent      | Model        | Used in                    |
| ---------- | ------------ | -------------------------- |
| filter     | gpt-4.1-mini | RSS/web ingest pipeline    |
| merge      | gpt-4.1-mini | RSS/web ingest pipeline    |
| inference  | gpt-4.1-mini | RSS/web ingest pipeline    |
| preference | gpt-4.1-mini | Scheduled (every 12h)      |
| microscope | o4-mini      | On-demand (user-triggered) |
| telescope  | o4-mini      | On-demand (user-triggered) |

## Token Estimates Per Call

Assumptions:

- Average RSS article: ~200 words (title + description) ≈ 270 tokens
- System prompt: ~150–200 tokens
- Preference profile: ~100 tokens
- Existing articles list (merge context): ~50 articles × 15 tokens = ~750 tokens

| Agent      | Input tokens                                                 | Output tokens         |
| ---------- | ------------------------------------------------------------ | --------------------- |
| filter     | ~570 (prompt 200 + profile 100 + article 270)                | ~50 (JSON)            |
| merge      | ~1,170 (prompt 150 + article 270 + existing 750)             | ~30 (JSON)            |
| inference  | ~570 (prompt 200 + profile 100 + article 270)                | ~200 (2–4 sentences)  |
| preference | ~2,500 (prompt 200 + 100 reactions × ~23 tokens)             | ~300 (profile text)   |
| microscope | ~770 (prompt 200 + profile 100 + feedback 200 + article 270) | ~800 (3–5 paragraphs) |
| telescope  | ~770 (same as microscope)                                    | ~800 (3–5 paragraphs) |

## Input

- 20 RSS feeds
- 5 web sources
- preference agent every 12h
- ~5 user-triggered analyses/day

**Pipeline assumptions:**

- Each RSS feed yields ~15 new articles/day (after title dedup)
- Each web source yields ~10 new articles/day
- ~60% pass the filter
- ~30% of filtered articles merge into existing items

### Daily Call Volume

| Stage      | Formula                | Calls/day |
| ---------- | ---------------------- | --------- |
| Filter     | 20 × 15 + 5 × 10       | 350       |
| Merge      | 350 × 0.6              | 210       |
| Inference  | 210 × 0.7 (non-merged) | 147       |
| Preference | 24h / 12h              | 2         |
| Microscope | user-triggered         | 5         |
| Telescope  | user-triggered         | 5         |

### Daily Token Usage

| Model        | Input tokens | Output tokens |
| ------------ | ------------ | ------------- |
| gpt-4.1-mini | 533,990      | 53,800        |
| o4-mini      | 7,700        | 8,000         |

### 💲 Daily Cost Breakdown

| Model        | Calculation                     | Cost                       |
| ------------ | ------------------------------- | -------------------------- |
| gpt-4.1-mini | $0.40 × 0.534 + $1.60 × 0.054 | **$0.30**                   |
| o4-mini      | $1.10 × 0.008 + $4.40 × 0.008 | **$0.04**                   |
| **Total**    |                                | **~$0.34/day → ~$10/month** |

## General Formula

```
daily_cost =
  (N_feeds × articles_per_feed + N_web × articles_per_web) × (
    filter_cost_per_call +
    pass_rate × merge_cost_per_call +
    pass_rate × (1 - merge_rate) × inference_cost_per_call
  ) +
  (24 / preference_interval_hours) × preference_cost_per_call +
  N_analyses × (microscope_cost + telescope_cost)
```

## Cost Optimization Levers

| Change                                      | Impact           |
| ------------------------------------------- | ---------------- |
| Reduce RSS feeds to 10                      | ~$6/month (−40%) |
| Tighter filter (40% pass rate)              | ~$7/month (−30%) |
| Upgrade inference to gpt-4.1                | ~$20/month (+$10 for higher quality) |
| Skip merge for feeds with <5 daily articles | minor savings    |
