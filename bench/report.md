# Cost benchmark

Measured 2026-11-08 against `ledgerline-514016` (BigQuery sandbox, no billing account).

## Method

Every number below is measured, not estimated:

1. `dbt build` records `bytes_processed` and `bytes_billed` from each BigQuery job response in `warehouse/target/run_results.json`.
2. `bench/queries/*.sql` are validated with a **dry run**, which returns the exact bytes scanned and bills nothing.
3. The paid figure applies the US on-demand rate of $6.25/TiB to the measured bytes.

## One pipeline run

- generated: `2026-11-08T13:04:10.808366Z`
- nodes: 72 (13 models, 57 tests)
- wall time: 34.8s
- bytes processed: 1.03 MiB
- bytes billed: 0.7227 GiB
- modeled paid cost: **$0.00441**

Billed is larger than processed because BigQuery's 10 MB minimum applies to each of the 72 statements. That floor, not the data, dominates this workload: the tables hold less than 1 MiB.

### Most expensive nodes

| Node | Processed (MiB) | Seconds |
|---|---:|---:|
| `fct_orders` | 0.161 | 3.38 |
| `fct_order_items` | 0.140 | 3.37 |
| `assert_non_negative_amounts` | 0.065 | 1.51 |
| `not_null_fct_order_items_order_item_key` | 0.061 | 1.52 |
| `unique_fct_order_items_order_item_key` | 0.061 | 2.17 |
| `relationships_fct_order_items_order_id__order_id__ref_fct_orders_` | 0.057 | 1.70 |
| `not_null_fct_order_items_order_id` | 0.041 | 1.54 |
| `fct_returns` | 0.032 | 3.19 |
| `dim_customers` | 0.031 | 3.26 |
| `relationships_fct_order_items_customer_id__customer_id__ref_dim_customers_` | 0.027 | 1.47 |

## Dashboard and reconciliation queries

| Query | Bytes scanned | Paid cost per run |
|---|---:|---:|
| `customer_ltv` | 0.044 MiB | $0.00006 |
| `dashboard_daily_revenue` | 0.017 MiB | $0.00006 |
| `reconciliation` | 0.035 MiB | $0.00006 |
| `refund_rate_by_category` | 0.046 MiB | $0.00006 |
| **all four** | **40.00 MiB billed** | **$0.00024** |

## Storage

Active logical bytes: **0.62 MiB** across 21 tables (staging views report 0).
Modeled storage cost: **$0.0000/month**.

<details><summary>Per table</summary>

| Table | Rows | Bytes |
|---|---:|---:|
| `marts.fct_order_items` | 2050 | 217300 |
| `raw.raw_order_items` | 2050 | 114800 |
| `marts.fct_orders` | 800 | 81015 |
| `ops.dq_results` | 280 | 60944 |
| `raw.raw_payments` | 773 | 53317 |
| `raw.raw_orders` | 800 | 41015 |
| `raw.raw_customers` | 500 | 32524 |
| `marts.dim_customers` | 500 | 32524 |
| `raw.raw_products` | 200 | 8566 |
| `marts.dim_products` | 200 | 8566 |
| `marts.fct_returns` | 20 | 1639 |
| `raw.raw_returns` | 20 | 1259 |
| `marts.dim_date` | 14 | 954 |
| `ops.load_audit` | 6 | 769 |
| `staging.int_order_financials` | 0 | 0 |
| `staging.stg_customers` | 0 | 0 |
| `staging.stg_order_items` | 0 | 0 |
| `staging.stg_orders` | 0 | 0 |
| `staging.stg_payments` | 0 | 0 |
| `staging.stg_products` | 0 | 0 |
| `staging.stg_returns` | 0 | 0 |

</details>

## Monthly projection (1 run/day)

| Item | Bytes billed / month | Paid cost / month |
|---|---:|---:|
| Pipeline (`dbt build`) | 21.7 GiB | $0.13 |
| Dashboard (4 queries, 24 loads/day) | 28.1 GiB | $0.17 |
| Storage | 0.0006 GiB | $0.00 |
| **Total** | | **$0.30** |

## Sandbox vs paid

| Constraint | Sandbox (this project) | Billed project |
|---|---|---|
| Query cost | free up to 1 TiB/month | $6.25/TiB on-demand |
| Storage | free up to 10 GiB | $0.02/GiB/month |
| DML / MERGE | rejected | allowed |
| Streaming inserts | rejected | allowed |
| Table expiry | 60 days | serverless, configurable |

The entire workload fits in the sandbox's free tier with room to spare: 0.0212 TiB of queries against a 1 TiB allowance. The free path is a policy choice, not a technical limit — the paid equivalent is cents per month.

## Caveats

- Prices are US multi-region on-demand list prices and change over time.
- The 10 MB minimum billed per statement is why the paid number is not the data size; at production volume the floor stops mattering.
- This is a 3-day, 800-orders/day demo. Scaling to 100k orders/day multiplies bytes roughly linearly for these row-wise models.
- Dry-run bytes equal billed bytes for a normal query (no cache, no clustering bonus applied).
