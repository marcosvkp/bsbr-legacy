/** Tipos das respostas da API BSBR (contrato exato do backend). */

export type ComponentKey = "total" | "acc" | "tech" | "speed";

export const COMPONENT_KEYS: readonly ComponentKey[] = ["total", "acc", "tech", "speed"];

export function isComponentKey(value: string | undefined | null): value is ComponentKey {
  return !!value && (COMPONENT_KEYS as readonly string[]).includes(value);
}

/** País filtrado no ranking (site é o ranking brasileiro). */
export const RANKING_COUNTRY = "BR";

// ---------------------------------------------------------------------------
// Rankings
// ---------------------------------------------------------------------------

export interface RankingItem {
  rank: number;
  ss_id: string;
  name: string;
  country: string;
  avatar_url: string | null;
  pp_total: number;
  pp_acc: number;
  pp_tech: number;
  pp_speed: number;
}

export interface RankingsResponse {
  component: ComponentKey;
  page: number;
  page_size: number;
  total: number;
  items: RankingItem[];
}

// ---------------------------------------------------------------------------
// Jogadores
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Stars Bands (faixas de 0.5★ com o melhor score de cada faixa)
// ---------------------------------------------------------------------------

export type StarsScope = "br" | "global";

export interface StarsBandTop {
  player_ss_id: string;
  player_name: string;
  player_country: string;
  avatar_url: string | null;
  map_name: string;
  map_hash: string;
  beatsaver_id: string | null;
  difficulty: string;
  stars: number;
  acc: number;
  pp: number;
}

export interface StarsBand {
  min: number;
  max: number;
  label: string;
  score_count: number;
  top: StarsBandTop;
}

export interface StarsBandsResponse {
  scope: StarsScope;
  step: number;
  bands: StarsBand[];
}

export interface PlayerMedals {
  total: number;
  maps_in_top10: number;
  best_rank: number | null;
}

export interface PlayerHistoryPoint {
  week: string;
  rank: number | null;
  pp_total: number | null;
  pp_acc: number | null;
  pp_tech: number | null;
  pp_speed: number | null;
}

export interface PlayerDetail {
  ss_id: string;
  name: string;
  country: string;
  avatar_url: string | null;
  rank: number | null;
  pp_total: number | null;
  pp_acc: number | null;
  pp_tech: number | null;
  pp_speed: number | null;
  medals: PlayerMedals;
  history: PlayerHistoryPoint[];
}

export interface PlayerScore {
  map_hash: string;
  map_name: string;
  cover_url: string | null;
  difficulty: string;
  total_stars: number | null;
  acc_stars: number | null;
  tech_stars: number | null;
  speed_stars: number | null;
  score: number;
  acc: number | null;
  full_combo: boolean;
  modifiers: string | null;
  pp: number | null;
  pp_acc: number | null;
  pp_tech: number | null;
  pp_speed: number | null;
  leaderboard_rank: number | null;
  time_set: string | null;
}

export interface PlayerScoresResponse {
  ss_id: string;
  page: number;
  page_size: number;
  has_more: boolean;
  items: PlayerScore[];
}

// ---------------------------------------------------------------------------
// Mapas
// ---------------------------------------------------------------------------

export interface DifficultySummary {
  name: string;
  total_stars: number | null;
  acc_stars: number | null;
  tech_stars: number | null;
  speed_stars: number | null;
  style_tags: string[];
  max_pp: number;
}

export interface MapSummary {
  hash: string;
  beatsaver_id: string;
  name: string;
  song_author: string;
  mapper: string;
  bpm: number | null;
  cover_url: string | null;
  tags: string[] | null;
  created_at: string | null;
  difficulties: DifficultySummary[];
}

export interface MapsResponse {
  page: number;
  page_size: number;
  total: number;
  items: MapSummary[];
}

export interface QualificationItem {
  id: number;
  hash: string;
  name: string;
  mapper: string | null;
  bpm: number | null;
  cover_url: string | null;
  status: "candidate" | "qualified";
  submitted_by: string | null;
  created_at: string | null;
  difficulties: Array<{
    name: string;
    total_stars: number | null;
    ss_leaderboard_id: string | null;
  }>;
}

export interface QualificationResponse {
  items: QualificationItem[];
}

export interface LeaderboardEntry {
  player_name: string;
  player_ss_id: string | null;
  avatar_url: string | null;
  difficulty: string;
  score: number;
  acc: number;
  full_combo: boolean;
  pp: number;
  pp_acc: number;
  pp_tech: number;
  pp_speed: number;
  leaderboard_rank: number | null;
}

export interface RatingHistoryEntry {
  difficulty_id: number | null;
  difficulty_name: string | null;
  total_before: number | null;
  total_after: number | null;
  acc_before: number | null;
  acc_after: number | null;
  tech_before: number | null;
  tech_after: number | null;
  speed_before: number | null;
  speed_after: number | null;
  reason: string;
  applied_by: string;
  applied_at: string | null;
}

export interface MapDetail extends MapSummary {
  difficulties_detail: Array<{
    name: string;
    njs: number | null;
    max_score: number | null;
    total_stars: number | null;
    acc_stars: number | null;
    tech_stars: number | null;
    speed_stars: number | null;
    style_tags: string[] | null;
    ranked_at: string | null;
  }>;
  leaderboard: LeaderboardEntry[];
  rating_history: RatingHistoryEntry[];
}

// ---------------------------------------------------------------------------
// Calculadora
// ---------------------------------------------------------------------------

export interface CalcResponse {
  pp_total: number;
  pp_acc: number;
  pp_tech: number;
  pp_speed: number;
}

export interface CalcGainResponse {
  raw_pp_needed: number;
  expected_weighted_gain: number;
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export interface ReweightSuggestion {
  id: number;
  difficulty_id: number;
  map_name: string | null;
  difficulty: string;
  current_stars: number | null;
  observed_acc: number | null;
  expected_acc: number | null;
  sample_size: number;
  delta_stars: number | null;
  suggested_stars: number | null;
  confidence: number | null;
  reason: string;
}

export interface SuggestionsResponse {
  status: string;
  items: ReweightSuggestion[];
}

export interface SuggestionActionResponse {
  id: number;
  status: string;
}

/** Stats retornadas por POST /admin/batch/run. */
export type BatchStats = Record<string, number>;

export interface AdminBatchItem {
  id: number;
  kind: string;
  started_at: string | null;
  finished_at: string | null;
  running: boolean;
  stats: BatchStats | null;
}

export interface AdminBatchesResponse {
  items: AdminBatchItem[];
}

// ---------------------------------------------------------------------------
// Scores ao vivo (scorefeed WebSocket)
// ---------------------------------------------------------------------------

export interface LiveScoreItem {
  source: "scoresaber" | "beatleader";
  score_id: string;
  leaderboard_id: string;
  player_id: string;
  player_name: string | null;
  song_hash: string | null;
  difficulty: string | null;
  score: number;
  acc: number | null;
  pp: number | null;
  mods: string;
  full_combo: boolean;
  max_score: number | null;
  rank: number | null;
  time_set: string;
  outcome?: Record<string, unknown> | null;
}

export interface LiveRecentResponse {
  items: LiveScoreItem[];
}

// ---------------------------------------------------------------------------
// Admin — qualificação de mapas (preview do ML + aprovação)
// ---------------------------------------------------------------------------

export interface QualifyPreviewMap {
  id: number;
  hash: string;
  name: string;
  mapper: string | null;
  bpm: number | null;
  status: string;
}

export interface QualifyPreviewDifficulty {
  id: number;
  name: string;
  total_stars: number | null;
  acc_stars: number | null;
  tech_stars: number | null;
  speed_stars: number | null;
  style_tags: string[] | null;
  ss_leaderboard_id: string | null;
  nps: number | null;
  notes: number | null;
}

export interface QualifyPreviewResponse {
  created: boolean;
  map: QualifyPreviewMap;
  difficulties: QualifyPreviewDifficulty[];
}

export interface AdminCandidate {
  id: number;
  hash: string;
  name: string;
  mapper: string | null;
  bpm: number | null;
  status: string;
  cover_url: string | null;
  submitted_by: string | null;
  created_at: string | null;
}

/** Coeficiente de ponderação do ranking: pp_ponderado = pp * 0.965^posicao. */
export const WEIGHT_COEFFICIENT = 0.965;

export function weightedAt(pp: number, position: number): number {
  return pp * WEIGHT_COEFFICIENT ** position;
}
