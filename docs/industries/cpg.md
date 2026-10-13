# Consumer packaged goods: Fennmoor Brands

Revenue and margin insight. API reference: `/docs/cpg`. Base path: `/cpg`.

## Data

4 categories, 14 brands, 47 SKUs, 6 regions and 6 channels. About 22,700 monthly sales facts cover the last 24 closed
months at SKU × region × channel grain, in USD at constant budget FX. The annual operating plan is held at brand ×
region × month (about 1,800 rows through December of the current year, 3 plan versions). Net revenue is about USD
11.4B over the last 12 months, with about 54% gross margin and a 21% trade rate. Dates are anchored to the container
start: the latest closed month is the previous calendar month.

## Data stories

| Story | Where to see it |
|---|---|
| Kumo Tea is up about 70% vs prior year in APAC North and APAC South in the latest quarter, strongest in Convenience and E-commerce, and about 30% ahead of plan. | `performance-summary` movers; `anomalies`; `plan-vs-actual` (Kumo Tea is furthest ahead) |
| Snacks gross margin in EMEA East falls from about 48% to 36-40% over 6 months of COGS inflation (39.6% in the latest quarter, 7.2 points below the prior year) while revenue still grows. | `performance-summary?region_ids=EMEA East` (margin-rate decline fact); `margin-bridge?category_ids=Snacks&breakdown_by=region` (cost effect concentrated in EMEA East); `anomalies` |
| E-commerce is the fastest-growing channel, about +33% vs prior year. | `performance-summary` "fastest-growing channel"; `query` grouped by channel with `compare=prior_year` |
| Personal Care list prices rose 8 months ago: Calvessa +7%, Tressora +6%, Orivant +4.5%. | `margin-bridge?category_ids=Personal Care&breakdown_by=brand` (price is the largest effect); `query` `gross_price_per_unit` by month (step change); assumptions in `/cpg/plan-versions` |
| North America beverages peak in July at about 1.8× January; LATAM and APAC South peak in January. | `query` net revenue by month for Beverages in North America |
| Jolterra in LATAM is down about 27% over the last 4 months during a distributor transition, about 30% behind plan. | `anomalies` (high severity); bottom brand × region movers |
| Lavendry in EMEA West loses volume to private label: revenue about -12%, trade rate +3.5 pts, about 16% behind plan year to date. | `performance-summary` bottom movers; `anomalies` (trade rate); `plan-vs-actual?region_ids=EMEA West` |
| Fizzwell Citrus Twist was delisted 5 months ago but is still in the plan; Fizzwell is the brand furthest behind plan. | `plan-vs-actual`; `/cpg/skus/SKU-10004` (discontinued) |

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"

# How did we do last quarter? (whole company, then EMEA only)
curl -s -H "$T" "$B/cpg/insights/performance-summary?period=latest_quarter"
curl -s -H "$T" "$B/cpg/insights/performance-summary?period=latest_quarter&region_ids=EMEA%20West,EMEA%20East"
# Why is Snacks margin down? Bridge by region
curl -s -H "$T" "$B/cpg/insights/margin-bridge?category_ids=Snacks&breakdown_by=region"
# Which brands are behind plan this year?
curl -s -H "$T" "$B/cpg/insights/plan-vs-actual?period=ytd&group_by=brand"
# What stands out this month?
curl -s -H "$T" "$B/cpg/insights/anomalies"
# Ad hoc: net revenue and gross margin by brand and region for two brands vs prior year
curl -s -H "$T" -H "$J" -X POST $B/cpg/query \
     -d '{"measures":["net_revenue","gross_margin_pct"],"group_by":["brand","region"],"filters":{"brand_ids":["Kumo Tea","Crunchwell"]},"compare":"prior_year"}'
# Where can I go next from Kumo Tea?
curl -s -H "$T" "$B/cpg/insights/drilldowns?dimension=brand&member=Kumo%20Tea"
```
