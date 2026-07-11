import fs from "node:fs";
import path from "node:path";
import type { DailyDigest } from "./types";

const DATA_ROOT = path.resolve(process.cwd(), "../data/digests");

function readJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(file, "utf8")) as T;
}

export interface DigestEntry { id: string; current: DailyDigest }
export interface DigestDay { id: string; date: string }

export function listDigests(): DigestEntry[] {
  if (!fs.existsSync(DATA_ROOT)) return [];
  return fs.readdirSync(DATA_ROOT)
    .filter((id) => fs.existsSync(path.join(DATA_ROOT, id, "current.json")))
    .map((id) => ({ id, current: readJson<DailyDigest>(path.join(DATA_ROOT, id, "current.json")) }));
}

export function loadDigest(id: string, date?: string): DailyDigest {
  const file = date
    ? path.join(DATA_ROOT, id, "days", date.slice(0, 4), date.slice(5, 7), `${date}.json`)
    : path.join(DATA_ROOT, id, "current.json");
  const digest = readJson<DailyDigest>(file);
  if (digest.schema_version !== 1) throw new Error(`Unsupported digest schema ${digest.schema_version}`);
  return digest;
}

export function listDays(): DigestDay[] {
  return listDigests().flatMap(({ id }) => {
    const index = readJson<{ dates: string[] }>(path.join(DATA_ROOT, id, "archive-index.json"));
    return index.dates.map((date) => ({ id, date }));
  });
}
