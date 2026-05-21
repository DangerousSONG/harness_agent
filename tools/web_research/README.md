# web_research

Research public web pages by crawling selected URLs with crawl4ai, converting page content to Markdown, and summarizing Markdown with Bailian/Qwen when configured.

## Flow

1. Use direct user-provided URLs when present.
2. Otherwise search for candidate URLs with a configured provider or no-key fallback search.
3. Crawl each selected URL through crawl4ai.
4. Preserve Markdown and crawl metadata.
5. Summarize Markdown only; raw HTML is never sent to the model.

## Outputs

- `search_mode`
- `urls_selected`
- `crawled_pages`: `title`, `url`, `markdown`, `crawl_status`, `extracted_at`, `content_length`
- `summary`
- `summary_provider`
- `citations`

## Configuration

- Optional: `SEARCH_PROVIDER`, `SEARCH_API_KEY_ENV`, provider-specific search credentials.
- Optional: `BAILIAN_API_KEY` or `DASHSCOPE_API_KEY` for Qwen summaries.
- Optional: `BAILIAN_BASE_URL`, `BAILIAN_MODEL`.

When Bailian/Qwen is not configured, the runtime returns Markdown excerpt summaries instead of failing.

## Safety

- Block `file://`, localhost, loopback, private-network, paywall-bypass, and secret-looking URLs.
- Do not send API keys, secrets, or private file contents as search queries.
- Do not bypass login walls or paywalls.
- Cite source URLs.
