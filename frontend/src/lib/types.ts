export type SourceState = "available" | "degraded" | "unavailable";

export interface Article {
  id: string;
  source_id: string;
  source_name: string;
  canonical_url: string;
  title: string;
  excerpt: string | null;
  published_at: string | null;
}

export interface SourceRun {
  source_id: string;
  source_name: string;
  state: SourceState;
  fetched: number;
  accepted: number;
  represented_events: number;
  history: number[];
}

export interface DigestEvent {
  id: string;
  slug: string;
  title: string;
  brief: string;
  context: string;
  why_it_matters: string;
  importance: number;
  status: "new" | "updated" | "disputed" | "completed";
  category: string;
  article_ids: string[];
  facts: Array<{ text: string; article_ids: string[] }>;
  updates: Array<{ at: string; summary: string; article_ids: string[] }>;
  first_seen_at: string;
  updated_at: string;
}

export interface DailyDigest {
  schema_version: number;
  digest_id: string;
  date: string;
  generated_at: string;
  daily_picture: { title: string; body: string };
  currencies: Array<{ pair: string; value: number; change_pct: number | null }>;
  sources: SourceRun[];
  articles: Article[];
  events: DigestEvent[];
}

