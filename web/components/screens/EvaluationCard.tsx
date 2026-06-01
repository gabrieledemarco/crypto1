"use client";
import React from 'react';
import { StrategyEvaluation } from '@/lib/api-types';
import styles from './EvaluationCard.module.css';

interface Props {
  evaluation: StrategyEvaluation;
  attempt: number;
}

export function EvaluationCard({ evaluation, attempt }: Props) {
  const { scores, overall_score, strengths, weaknesses, specific_improvements, fatal_flaws, verdict, verdict_rationale } = evaluation;

  const scoreColor = (s: number) => s >= 4 ? '#22c55e' : s >= 3 ? '#f59e0b' : '#ef4444';

  const verdictColor = verdict === 'promote' ? '#22c55e' : verdict === 'iterate' ? '#f59e0b' : '#ef4444';

  const scoreLabels: Record<string, string> = {
    alpha_source: 'Alpha Source',
    signal_logic: 'Signal Logic',
    risk_management: 'Risk Mgmt',
    regime_sensitivity: 'Regime Fit',
    statistical_robustness: 'Robustness',
    implementation_quality: 'Code Quality',
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.title}>Expert Evaluation · Attempt {attempt}</span>
        <span className={styles.verdict} style={{ color: verdictColor }}>
          {verdict.toUpperCase()}
        </span>
        <span className={styles.overall}>{overall_score.toFixed(1)}/10</span>
      </div>

      <div className={styles.scores}>
        {Object.entries(scores).map(([key, value]) => (
          <div key={key} className={styles.scoreRow}>
            <span className={styles.scoreLabel}>{scoreLabels[key] ?? key}</span>
            <div className={styles.scoreBar}>
              <div
                className={styles.scoreFill}
                style={{ width: `${(value / 5) * 100}%`, backgroundColor: scoreColor(value) }}
              />
            </div>
            <span className={styles.scoreValue} style={{ color: scoreColor(value) }}>{value}/5</span>
          </div>
        ))}
      </div>

      <p className={styles.rationale}>{verdict_rationale}</p>

      {strengths.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>&#10003; Strengths</div>
          {strengths.map((s, i) => <div key={i} className={styles.strength}>{s}</div>)}
        </div>
      )}

      {weaknesses.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>&#9888; Weaknesses</div>
          {weaknesses.map((w, i) => <div key={i} className={styles.weakness}>{w}</div>)}
        </div>
      )}

      {fatal_flaws.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>&#10007; Fatal Flaws</div>
          {fatal_flaws.map((f, i) => <div key={i} className={styles.flaw}>{f}</div>)}
        </div>
      )}

      {specific_improvements.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>&#8594; Improvements</div>
          {specific_improvements.map((imp, i) => <div key={i} className={styles.improvement}>{imp}</div>)}
        </div>
      )}
    </div>
  );
}
