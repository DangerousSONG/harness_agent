# web_search

Search the web for current information, crawl selected URLs with crawl4ai, convert page content to Markdown, and return cited summaries.

## Purpose

`web_search` provides the `web_search` capability for workspace workflows.

## Inputs

- `query`: string.
- `urls`: array.
- `max_results`: integer.
- `language`: string.
- `recency`: string.

## Outputs

- `results`: array.
- `crawled_pages`: array of `{title, url, markdown, crawl_status, extracted_at, content_length}`.
- `summary`: string.
- `summary_provider`: string.
- `citations`: array.
- `retrieved_at`: string.

## Provider Configuration

Search provider configuration is optional because the runtime can try no-key fallback search. Configure `SEARCH_PROVIDER` and provider credentials for better coverage and reliability.

Provider credentials must be configured outside the repository and read from the runtime environment.

## Safety Rules

- Do not fabricate search results.
- Always crawl selected URLs through crawl4ai and summarize Markdown, not raw HTML.
- Cite sources when used in answers.
- Do not send secrets or private files as query text.
- Block file://, localhost, loopback, private-network, paywall-bypass, and secret-looking URLs.
- Respect workspace and provider policy.

## Example Call

```json
{
  "tool": "web_search",
  "input": {
    "query": "OpenAI latest model",
    "max_results": 5,
    "language": "zh-CN"
  }
}
```
