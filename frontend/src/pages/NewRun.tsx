import React, { useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  HelpCircle,
  Info,
  UploadCloud,
} from 'lucide-react';
import { api } from '../lib/api';
import type { CreateRunRequest, CSVValidationResponse } from '../types';

interface NewRunProps {
  onRunCreated: (runId: string) => void;
  onCancel: () => void;
}

export const NewRun: React.FC<NewRunProps> = ({ onRunCreated, onCancel }) => {
  // Wizard state
  const [sourceType, setSourceType] = useState<'simulation' | 'csv' | 'api'>('simulation');

  // Form parameters
  const [scenario, setScenario] = useState<CreateRunRequest['scenario']>('abrupt');
  const [nEvents, setNEvents] = useState<number>(10000);
  const [seed, setSeed] = useState<number>(42);
  const [eventsPerSecond, setEventsPerSecond] = useState<number>(100);

  // Scenario specific
  const [driftStart, setDriftStart] = useState<number>(1000);
  const [gradualWindow, setGradualWindow] = useState<number>(500);
  const [recurrenceInterval, setRecurrenceInterval] = useState<number>(1000);
  const [rareRegionP, setRareRegionP] = useState<number>(0.03);
  const [adversaryDwell, setAdversaryDwell] = useState<number>(500);

  // Label Policy
  const [monitorRate, setMonitorRate] = useState<number>(15);
  const [targetTrainingLabels, setTargetTrainingLabels] = useState<number>(200);
  const [evaluationTargetEvents] = useState<number>(500);
  const [labelBudget, setLabelBudget] = useState<number>(2000);
  const [labelDelay, setLabelDelay] = useState<number>(0);

  // CSV Replay State
  const [csvContent, setCsvContent] = useState<string>('');
  const [csvFileName, setCsvFileName] = useState<string>('');
  const [csvValidation, setCsvValidation] = useState<CSVValidationResponse | null>(null);
  const [feature0, setFeature0] = useState<string>('');
  const [feature1, setFeature1] = useState<string>('');
  const [labelCol, setLabelCol] = useState<string>('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    try {
      const text = await file.text();
      setCsvContent(text);
      setCsvFileName(file.name);
      const res = await api.validateCSV(text);
      setCsvValidation(res);
      setFeature0(res.detected_mappings.feature_0 || res.columns[0] || '');
      setFeature1(res.detected_mappings.feature_1 || res.columns[1] || '');
      setLabelCol(res.detected_mappings.label || '');
    } catch (err: any) {
      setError(err?.message || 'CSV validation failed.');
      setCsvValidation(null);
    }
  };

  const getScenarioDescription = () => {
    switch (scenario) {
      case 'stationary':
        return 'Simulated stationary sensor stream with no concept shift. Tests false alarm resistance.';
      case 'abrupt':
        return 'Simulated equipment sensor data with a sudden decision boundary change at configured event.';
      case 'gradual':
        return 'Continuous linear transition between pre-drift and post-drift distributions across a window.';
      case 'recurring':
        return 'Periodic alternation between concept A and concept B at fixed intervals.';
      case 'rare_region':
        return 'Localized stealth perturbation affecting only a small subpopulation probability mass.';
      case 'adversary':
        return 'Margin-adaptive adversary perturbing observations close to the decision boundary.';
      default:
        return 'Simulated numerical sensor stream.';
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    if (sourceType === 'csv') {
      if (!csvContent || !csvValidation) {
        setError('Please upload and validate a CSV dataset file before starting stream replay.');
        setIsSubmitting(false);
        return;
      }
      try {
        const run = await api.createCSVRun({
          csv_content: csvContent,
          feature_0: feature0,
          feature_1: feature1,
          label: labelCol || null,
          warmup_size: 200,
          label_budget: labelBudget,
          label_delay: labelDelay,
          monitor_rate: monitorRate / 100,
          events_per_second: eventsPerSecond,
        });
        await api.controlRun(run.run_id, 'start', eventsPerSecond);
        onRunCreated(run.run_id);
      } catch (err: any) {
        setError(err?.message || 'Failed to initialize and start CSV stream replay.');
        setIsSubmitting(false);
      }
      return;
    }

    const payload: CreateRunRequest = {
      scenario,
      n_events: nEvents,
      warmup_size: 200,
      label_budget: labelBudget,
      label_delay: labelDelay,
      monitor_rate: monitorRate / 100,
      seed,
      events_per_second: eventsPerSecond,
      target_training_labels: targetTrainingLabels,
      evaluation_target_events: evaluationTargetEvents,
    };

    if (scenario === 'abrupt' || scenario === 'gradual' || scenario === 'recurring' || scenario === 'rare_region') {
      payload.drift_start_sequence = driftStart;
    }
    if (scenario === 'gradual') payload.gradual_window = gradualWindow;
    if (scenario === 'recurring') payload.recurrence_interval = recurrenceInterval;
    if (scenario === 'rare_region') payload.rare_region_p = rareRegionP;
    if (scenario === 'adversary') payload.adversary_dwell = adversaryDwell;

    try {
      const run = await api.createRun(payload);
      // Auto-start run
      await api.controlRun(run.run_id, 'start', eventsPerSecond);
      onRunCreated(run.run_id);
    } catch (err: any) {
      setError(err?.message || 'Failed to initialize and start stream.');
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {/* Header */}
      <div>
        <h1 style={{ fontSize: '1.625rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
          Connect a stream
        </h1>
        <div style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', marginTop: '0.125rem' }}>
          Define your input, labels, and monitoring budget.
        </div>
      </div>

      {/* Stepper Progress Wizard */}
      <div className="stepper-container">
        <div className="stepper-step completed">
          <span style={{ width: '20px', height: '20px', borderRadius: '50%', backgroundColor: 'var(--cobalt-600)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.6875rem' }}>
            1
          </span>
          <span>Source</span>
        </div>
        <div className="stepper-divider" />
        <div className="stepper-step active">
          <span style={{ width: '20px', height: '20px', borderRadius: '50%', border: '1px solid var(--cobalt-600)', color: 'var(--cobalt-600)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.6875rem' }}>
            2
          </span>
          <span>Schema</span>
        </div>
        <div className="stepper-divider" />
        <div className="stepper-step">
          <span style={{ width: '20px', height: '20px', borderRadius: '50%', border: '1px solid var(--border-strong)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.6875rem' }}>
            3
          </span>
          <span>Labels</span>
        </div>
        <div className="stepper-divider" />
        <div className="stepper-step">
          <span style={{ width: '20px', height: '20px', borderRadius: '50%', border: '1px solid var(--border-strong)', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.6875rem' }}>
            4
          </span>
          <span>Start</span>
        </div>
      </div>

      {error && (
        <div className="card" style={{ backgroundColor: 'var(--danger-bg)', borderColor: 'var(--danger-border)', color: 'var(--danger-text)', padding: '0.75rem 1rem', fontSize: '0.8125rem' }}>
          {error}
        </div>
      )}

      {/* 2-Column Form Body */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1.25rem' }}>
        {/* Left Column: Source Configuration */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Source configuration
          </div>

          {/* Source Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', gap: '1.5rem' }}>
            <button
              type="button"
              onClick={() => setSourceType('simulation')}
              style={{
                background: 'none',
                border: 'none',
                borderBottom: sourceType === 'simulation' ? '2px solid var(--cobalt-600)' : '2px solid transparent',
                padding: '0.5rem 0.25rem',
                fontSize: '0.8125rem',
                fontWeight: sourceType === 'simulation' ? 600 : 500,
                color: sourceType === 'simulation' ? 'var(--cobalt-600)' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              Simulation
            </button>
            <button
              type="button"
              onClick={() => setSourceType('csv')}
              style={{
                background: 'none',
                border: 'none',
                borderBottom: sourceType === 'csv' ? '2px solid var(--cobalt-600)' : '2px solid transparent',
                padding: '0.5rem 0.25rem',
                fontSize: '0.8125rem',
                fontWeight: sourceType === 'csv' ? 600 : 500,
                color: sourceType === 'csv' ? 'var(--cobalt-600)' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              CSV replay <span style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>(MVP Simulation)</span>
            </button>
            <button
              type="button"
              disabled
              style={{
                background: 'none',
                border: 'none',
                padding: '0.5rem 0.25rem',
                fontSize: '0.8125rem',
                color: 'var(--text-muted)',
                opacity: 0.5,
                cursor: 'not-allowed',
              }}
            >
              Live API
            </button>
          </div>

          {/* Source Parameters depending on sourceType */}
          {sourceType === 'csv' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Upload CSV dataset file</label>
                <div
                  style={{
                    border: '2px dashed var(--cobalt-600)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '1.25rem',
                    textAlign: 'center',
                    backgroundColor: 'var(--bg-surface-subtle)',
                    cursor: 'pointer',
                    position: 'relative',
                  }}
                >
                  <input
                    type="file"
                    accept=".csv"
                    onChange={handleFileChange}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      opacity: 0,
                      cursor: 'pointer',
                    }}
                  />
                  <UploadCloud size={24} color="var(--cobalt-600)" style={{ margin: '0 auto 0.5rem auto' }} />
                  <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {csvFileName ? `Selected: ${csvFileName}` : 'Choose CSV File or Drag & Drop'}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    Supports plain text .csv files (10 to 50,000 rows, max 50 MB)
                  </div>
                </div>
              </div>

              {csvValidation && (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.8125rem', color: 'var(--success-text)', backgroundColor: 'var(--success-bg)', padding: '0.5rem 0.75rem', borderRadius: 'var(--radius-sm)' }}>
                    <span style={{ fontWeight: 600 }}>✓ Dataset Validated ({csvValidation.total_rows} rows)</span>
                    <span>{csvValidation.columns.length} columns detected</span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.75rem' }}>
                    <div className="form-group">
                      <label className="form-label">Feature 0 Column</label>
                      <select className="form-select" value={feature0} onChange={(e) => setFeature0(e.target.value)}>
                        {csvValidation.columns.map((col) => (
                          <option key={col} value={col}>{col}</option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Feature 1 Column</label>
                      <select className="form-select" value={feature1} onChange={(e) => setFeature1(e.target.value)}>
                        {csvValidation.columns.map((col) => (
                          <option key={col} value={col}>{col}</option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Target / Label Column</label>
                      <select className="form-select" value={labelCol} onChange={(e) => setLabelCol(e.target.value)}>
                        <option value="">(None - default 0)</option>
                        {csvValidation.columns.map((col) => (
                          <option key={col} value={col}>{col}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </>
              )}

              <div className="form-group">
                <label className="form-label">Events / sec speed</label>
                <input
                  type="number"
                  className="form-input"
                  value={eventsPerSecond}
                  onChange={(e) => setEventsPerSecond(parseInt(e.target.value) || 100)}
                />
              </div>
            </div>
          ) : (
            <>
              {/* Scenario Selection */}
              <div className="form-group">
                <label className="form-label">Scenario</label>
                <select
                  className="form-select"
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value as any)}
                >
                  <option value="abrupt">Equipment state — abrupt boundary shift</option>
                  <option value="stationary">Stationary monitoring baseline (no drift)</option>
                  <option value="gradual">Gradual concept transition</option>
                  <option value="recurring">Recurring concept alternation</option>
                  <option value="rare_region">Rare-region stealth drift (p=0.03)</option>
                  <option value="adversary">Adaptive adversary (margin evasion)</option>
                </select>
                <div className="form-help">{getScenarioDescription()}</div>
              </div>

              {/* Seed & Event Rate & Total Events */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.75rem' }}>
                <div className="form-group">
                  <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    Total Events
                  </label>
                  <input
                    type="number"
                    className="form-input"
                    value={nEvents}
                    onChange={(e) => setNEvents(parseInt(e.target.value) || 10000)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    Random seed <HelpCircle size={12} color="var(--text-muted)" />
                  </label>
                  <input
                    type="number"
                    className="form-input"
                    value={seed}
                    onChange={(e) => setSeed(parseInt(e.target.value) || 42)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Events / sec</label>
                  <input
                    type="number"
                    className="form-input"
                    value={eventsPerSecond}
                    onChange={(e) => setEventsPerSecond(parseInt(e.target.value) || 100)}
                  />
                </div>
              </div>

              {/* Scenario Specific Parameters */}
              {scenario !== 'stationary' && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1rem' }}>
                  <div className="form-group">
                    <label className="form-label">Drift Start Sequence</label>
                    <input
                      type="number"
                      className="form-input"
                      value={driftStart}
                      onChange={(e) => setDriftStart(parseInt(e.target.value) || 1000)}
                    />
                  </div>

                  {scenario === 'gradual' && (
                    <div className="form-group">
                      <label className="form-label">Gradual Window (Events)</label>
                      <input
                        type="number"
                        className="form-input"
                        value={gradualWindow}
                        onChange={(e) => setGradualWindow(parseInt(e.target.value) || 500)}
                      />
                    </div>
                  )}

                  {scenario === 'recurring' && (
                    <div className="form-group">
                      <label className="form-label">Recurrence Interval</label>
                      <input
                        type="number"
                        className="form-input"
                        value={recurrenceInterval}
                        onChange={(e) => setRecurrenceInterval(parseInt(e.target.value) || 1000)}
                      />
                    </div>
                  )}

                  {scenario === 'rare_region' && (
                    <div className="form-group">
                      <label className="form-label">Rare Mass (p)</label>
                      <input
                        type="number"
                        step="0.01"
                        className="form-input"
                        value={rareRegionP}
                        onChange={(e) => setRareRegionP(parseFloat(e.target.value) || 0.03)}
                      />
                    </div>
                  )}

                  {scenario === 'adversary' && (
                    <div className="form-group">
                      <label className="form-label">Adversary Dwell (Events)</label>
                      <input
                        type="number"
                        className="form-input"
                        value={adversaryDwell}
                        onChange={(e) => setAdversaryDwell(parseInt(e.target.value) || 500)}
                      />
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Feature Tags */}
          <div className="form-group">
            <label className="form-label">Features (2)</label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <span className="badge badge-info" style={{ textTransform: 'none', fontSize: '0.75rem', padding: '0.25rem 0.625rem' }}>
                vibration_rms
              </span>
              <span className="badge badge-info" style={{ textTransform: 'none', fontSize: '0.75rem', padding: '0.25rem 0.625rem' }}>
                temperature_c
              </span>
            </div>
          </div>

          {/* Optional CSV Replay Box */}
          <div
            style={{
              border: '1px dashed var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '1rem',
              textAlign: 'center',
              backgroundColor: 'var(--bg-surface-subtle)',
              marginTop: '0.5rem',
            }}
          >
            <UploadCloud size={20} color="var(--cobalt-600)" style={{ margin: '0 auto 0.25rem auto' }} />
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Drop a CSV to replay a recorded stream (optional)
            </div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.125rem' }}>
              Or click to browse. Supports .csv files up to 200 MB. (Using verified synthetic generator)
            </div>
          </div>
        </div>

        {/* Right Column: Label Policy */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Label policy
            </span>
            <HelpCircle size={14} color="var(--text-muted)" />
          </div>

          {/* Random Monitoring */}
          <div className="form-group">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <label className="form-label">Random monitoring</label>
                <div className="form-help">Randomly sample events for monitoring labels.</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', width: '90px' }}>
                <input
                  type="number"
                  className="form-input"
                  style={{ textAlign: 'right', padding: '0.375rem 0.5rem' }}
                  value={monitorRate}
                  onChange={(e) => setMonitorRate(parseInt(e.target.value) || 15)}
                />
                <span style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>%</span>
              </div>
            </div>
          </div>

          {/* Candidate Training Quota */}
          <div className="form-group">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <label className="form-label">Uncertainty training quota</label>
                <div className="form-help">Post-alert target labels to freeze candidate model.</div>
              </div>
              <input
                type="number"
                className="form-input"
                style={{ width: '90px', textAlign: 'right', padding: '0.375rem 0.5rem' }}
                value={targetTrainingLabels}
                onChange={(e) => setTargetTrainingLabels(parseInt(e.target.value) || 200)}
              />
            </div>
          </div>

          {/* Total Label Budget */}
          <div className="form-group">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <label className="form-label">Total label budget</label>
                <div className="form-help">Total number of labels to collect (monitoring + training).</div>
              </div>
              <input
                type="number"
                className="form-input"
                style={{ width: '90px', textAlign: 'right', padding: '0.375rem 0.5rem' }}
                value={labelBudget}
                onChange={(e) => setLabelBudget(parseInt(e.target.value) || 1200)}
              />
            </div>
          </div>

          {/* Label Delay */}
          <div className="form-group">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <label className="form-label">Label delay (events)</label>
                <div className="form-help">Delay between event time and label arrival.</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', width: '90px' }}>
                <input
                  type="number"
                  className="form-input"
                  style={{ textAlign: 'right', padding: '0.375rem 0.5rem' }}
                  value={labelDelay}
                  onChange={(e) => setLabelDelay(parseInt(e.target.value) || 0)}
                />
                <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>evts</span>
              </div>
            </div>
          </div>

          {/* Informative Callout */}
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.625rem',
              backgroundColor: 'var(--info-bg)',
              border: '1px solid var(--info-border)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.75rem',
              fontSize: '0.75rem',
              color: 'var(--info-text)',
              marginTop: 'auto',
            }}
          >
            <Info size={16} style={{ flexShrink: 0, marginTop: '0.1rem' }} />
            <div>
              <strong>Monitoring labels are sampled independently.</strong> Monitoring and training labels are drawn from separate random processes.
            </div>
          </div>
        </div>
      </div>

      {/* Schema Preview Table */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <div>
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Schema preview
            </span>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Preview of generated events. This schema will be used for the stream.
            </div>
          </div>
          <span className="badge badge-success">
            <CheckCircle2 size={12} /> 0 errors
          </span>
        </div>

        <div className="table-wrapper">
          {csvValidation ? (
            <table className="table">
              <thead>
                <tr>
                  {csvValidation.columns.map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {csvValidation.preview_rows.map((row, idx) => (
                  <tr key={idx}>
                    {csvValidation.columns.map((col) => (
                      <td key={col} style={{ fontFamily: 'var(--font-mono)' }}>
                        {String(row[col] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>event_id</th>
                  <th>event_time</th>
                  <th>vibration_rms</th>
                  <th>temperature_c</th>
                  <th>status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>1000001</td>
                  <td>2024-06-15 10:00:00.000</td>
                  <td>0.482</td>
                  <td>52.1</td>
                  <td>Normal</td>
                </tr>
                <tr>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>1000002</td>
                  <td>2024-06-15 10:00:00.010</td>
                  <td>0.517</td>
                  <td>51.8</td>
                  <td>Normal</td>
                </tr>
                <tr>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>1000003</td>
                  <td>2024-06-15 10:00:00.020</td>
                  <td>1.204</td>
                  <td>63.5</td>
                  <td>Inspect</td>
                </tr>
                <tr>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>1000004</td>
                  <td>2024-06-15 10:00:00.030</td>
                  <td>0.911</td>
                  <td>58.7</td>
                  <td>Normal</td>
                </tr>
                <tr>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>1000005</td>
                  <td>2024-06-15 10:00:00.040</td>
                  <td>1.423</td>
                  <td>66.2</td>
                  <td>Inspect</td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Footer Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '0.5rem' }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onCancel}
        >
          Back
        </button>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={isSubmitting}
          style={{ fontWeight: 600, padding: '0.5rem 1.25rem' }}
        >
          {isSubmitting ? 'Initializing...' : 'Validate & start stream'} <ArrowRight size={14} />
        </button>
      </div>
    </form>
  );
};
