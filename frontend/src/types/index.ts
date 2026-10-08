/**
 * Type definitions matching backend REST schemas and WebSocket snapshots.
 */

export interface CreateRunRequest {
  scenario: 'stationary' | 'abrupt' | 'gradual' | 'recurring' | 'rare_region' | 'adversary';
  n_events: number;
  warmup_size: number;
  label_budget: number;
  label_delay: number;
  monitor_rate?: number;
  seed: number;
  drift_start_sequence?: number | null;
  gradual_window?: number | null;
  recurrence_interval?: number | null;
  rare_region_p?: number | null;
  adversary_dwell?: number | null;
  adwin_delta?: number;
  target_training_labels?: number;
  evaluation_target_events?: number;
  events_per_second?: number;
  run_id?: string | null;
  parent_run_id?: string | null;
  idempotency_key?: string | null;
}

export interface CSVValidationResponse {
  valid: boolean;
  total_rows: number;
  columns: string[];
  detected_mappings: {
    feature_0: string | null;
    feature_1: string | null;
    label: string | null;
  };
  preview_rows: Record<string, any>[];
}

export interface CreateCSVRunRequest {
  csv_content: string;
  feature_0: string;
  feature_1: string;
  label?: string | null;
  warmup_size?: number;
  label_budget?: number;
  label_delay?: number;
  monitor_rate?: number;
  adwin_delta?: number;
  target_training_labels?: number;
  evaluation_target_events?: number;
  events_per_second?: number;
  run_id?: string | null;
}

export interface ControlRequest {
  action: 'start' | 'pause' | 'resume' | 'stop';
  events_per_second?: number | null;
}

export interface ControlResponse {
  run_id: string;
  action: string;
  previous_state: string;
  current_state: string;
  message: string;
}

export interface LabelAccounting {
  warmup_acquisitions: number;
  monitor_acquisitions: number;
  selective_acquisitions: number;
  post_warmup_acquisitions: number;
  total_unique_acquisitions: number;
  budget_debits: number;
}

export interface ClassificationMetric {
  sample_count: number;
  correct_count: number;
  incorrect_count: number;
  denominator: number;
  error_rate: number | null;
}

export interface IncidentItem {
  incident_id: string;
  run_id: string;
  alert_type: string;
  event_id: string;
  event_sequence: number;
  arrival_sequence: number;
  detection_delay: number;
  model_version: string;
  candidate_id?: string | null;
  outcome?: string | null;
  evidence: Record<string, any>;
  created_at: number;
}

export interface CandidateDetail {
  candidate_id: string;
  target_version?: string;
  state: string;
  unique_training_labels: number;
  target_training_labels: number;
  progress_percent: number;
  epoch?: number;
  freeze_sequence?: number | null;
}

export interface PairedSessionDetail {
  eval_id: string;
  candidate_id: string;
  candidate_version?: string;
  decision: string;
  gain?: number | null;
  p_value?: number | null;
  b: number;
  c: number;
  n: number;
  delivered_labels_count: number;
  target_events_count: number;
  progress_percent: number;
}

export interface MonitoringSummary {
  alerts_count: number;
  alerts: Array<{
    alert_id: string;
    arrival_sequence: number;
    description: string;
    outcome?: string | null;
  }>;
}

export interface CandidateSummary {
  total_candidates_spawned?: number;
  candidates_count?: number;
  candidates?: CandidateDetail[];
}

export interface PairedSummary {
  completed_comparisons_count: number;
  sessions?: PairedSessionDetail[];
}

export interface RunSummary {
  run_id: string;
  parent_run_id?: string | null;
  scenario: string;
  seed: number;
  mode: string;
  state: string;
  created_at: number;
  updated_at: number;
  completed_at?: number | null;
  config?: Record<string, any>;
}

export interface RunDetail {
  run_id: string;
  parent_run_id?: string | null;
  scenario: string;
  seed: number;
  mode: string;
  schema_version: string;
  state: string;
  operational_state: string;
  candidate_state?: string;
  active_model_version: string;
  events_processed: number;
  total_events: number;
  progress_percent: number;
  monitoring_coverage: number;
  synthetic_data: boolean;
  created_at: number;
  updated_at: number;
  completed_at?: number | null;
  config: Record<string, any>;
  environment: Record<string, any>;
  label_accounting: LabelAccounting;
  monitoring_summary?: MonitoringSummary | null;
  candidate_summary?: CandidateSummary | null;
  paired_summary?: PairedSummary | null;
  metrics?: Record<string, ClassificationMetric> | null;
}

export interface WebSocketSnapshotMessage {
  run_id: string;
  schema_version: string;
  snapshot_sequence: number;
  operational_state: string;
  candidate_state?: string | null;
  events_processed: number;
  total_events: number;
  progress_percent: number;
  active_model_version: string;
  monitoring_coverage: number;
  label_accounting: LabelAccounting;
  metrics?: Record<string, ClassificationMetric> | null;
  monitoring_summary?: MonitoringSummary | null;
  candidate_summary?: CandidateSummary | null;
  paired_summary?: PairedSummary | null;
  synthetic_data: boolean;
  timestamp: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface HealthStatus {
  status: string;
  storage_ready: boolean;
  active_run_id?: string | null;
  timestamp: number;
}

// -----------------------------------------------------------------------
// Theory Lab Types (Phase 6B)
// -----------------------------------------------------------------------

export interface CreateRareRegionRequest {
  mode: 'rare-region';
  p: number;
  q: number;
  deadline: number;
  delta: number;
  trials: number;
  seed: number;
  query_seed?: number | null;
  no_change?: boolean;
}

export interface CreateFiniteDomainRequest {
  mode: 'finite-domain';
  n_domain: number;
  scenario: 'no-change' | 'single-last' | 'multiple' | 'custom';
  changed_indices?: number[] | null;
  query_order?: number[] | null;
  seed: number;
}

export type CreateTheoryRequest = CreateRareRegionRequest | CreateFiniteDomainRequest;

export interface TheoryExperimentSummary {
  experiment_id: string;
  mode: 'rare-region' | 'finite-domain';
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'INTERRUPTED';
  seed: number;
  config: Record<string, any>;
  artifacts_dir: string;
  summary_artifact_path?: string | null;
  data_artifact_path?: string | null;
  error_message?: string | null;
  created_at: number;
  updated_at: number;
  completed_at?: number | null;
}

export interface TrialRecord {
  trial_index: number;
  detected: boolean;
  detection_delay: number | null;
  labels_acquired: number;
  total_events: number;
  queried_disagreements: number;
  unqueried_disagreements: number;
}

export interface RareRegionResults {
  result_type?: 'rare-region';
  parameters: {
    p: number;
    q: number;
    deadline: number;
    delta: number;
    trials: number;
    seed: number;
    query_seed?: number | null;
    no_change?: boolean;
  };
  theoretical: {
    miss_probability: number;
    detection_probability: number;
    min_deadline_for_delta: number | null;
    uncensored_expected_detection_time: number | null;
    conditional_expected_detection_time: number | null;
    expected_observation_time: number;
    expected_acquired_labels: number;
    expected_stream_events_to_detection?: number | null;
    expected_labels_to_detection?: number | null;
  };
  empirical: {
    trials_count: number;
    miss_count: number;
    miss_frequency: number;
    detection_count: number;
    detection_frequency: number;
    confidence_interval_95: [number, number];
    mean_detection_delay: number | null;
    mean_observation_time: number;
    mean_labels_acquired: number;
    total_labels_acquired: number;
  };
  trials_sample?: TrialRecord[];
}

export interface AuditQueryRecord {
  query_sequence: number;
  input_id: number;
  queried_label: number;
  old_rule_label: number;
  disagreement_detected: boolean;
  audit_progress: number;
  is_audit_complete: boolean;
  cumulative_changes_discovered: number;
}

export interface FiniteDomainResults {
  result_type?: 'finite-domain';
  total_domain_size: number;
  queries_completed: number;
  is_complete: boolean;
  unique_label_cost: number;
  discovered_change_indices: number[];
  total_discovered_changes: number;
  evaluator_true_changed_indices: number[];
  evaluator_all_labels_correct: boolean;
  records: AuditQueryRecord[];
}

export interface TheoryExperimentDetail extends TheoryExperimentSummary {
  results?: RareRegionResults | FiniteDomainResults | Record<string, any> | null;
}

export interface PaginatedTheoryExperimentsResponse {
  items: TheoryExperimentSummary[];
  total: number;
  limit: number;
  offset: number;
}
