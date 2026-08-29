"use client";

import { useState } from "react";
import { ApiError, postJson } from "@/lib/api";
import type { CalcGainResponse, CalcResponse } from "@/lib/types";
import { formatPp } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { COMPONENT_META, type SubComponentKey } from "@/components/pp-meta";

export interface CalculatorProps {
  /** PPs crus dos scores do jogador (entrada da calculadora +1pp). */
  scoresPps: number[];
}

const INPUT_CLASSES =
  "h-9 w-full rounded-md border border-border-subtle bg-background px-3 text-sm text-foreground tabular-nums placeholder:text-muted/60 focus:border-secondary focus:outline-none";

const SHARE_FIELDS = [
  { key: "share_acc" as const, label: "% Acc", meta: COMPONENT_META.acc },
  { key: "share_tech" as const, label: "% Tech", meta: COMPONENT_META.tech },
  { key: "share_speed" as const, label: "% Speed", meta: COMPONENT_META.speed },
];

/** Calculadora de PP: decomposição por estilo + estimativa de +1pp ponderado. */
export function Calculator({ scoresPps }: CalculatorProps) {
  const [stars, setStars] = useState("11.00");
  const [accuracy, setAccuracy] = useState("95.00");
  const [shares, setShares] = useState({ share_acc: "34", share_tech: "33", share_speed: "33" });
  const [calc, setCalc] = useState<CalcResponse | null>(null);
  const [gain, setGain] = useState<CalcGainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const starsNum = Number.parseFloat(stars);
    const accNum = Number.parseFloat(accuracy);
    const shareNums = {
      share_acc: Number.parseFloat(shares.share_acc),
      share_tech: Number.parseFloat(shares.share_tech),
      share_speed: Number.parseFloat(shares.share_speed),
    };

    if (!Number.isFinite(starsNum) || starsNum <= 0) {
      setError("Estrelas deve ser um número positivo.");
      return;
    }
    if (!Number.isFinite(accNum) || accNum <= 0 || accNum > 100) {
      setError("Accuracy deve estar entre 0 e 100.");
      return;
    }
    const shareSum = shareNums.share_acc + shareNums.share_tech + shareNums.share_speed;
    if (Math.abs(shareSum - 100) > 0.5) {
      setError(`Os percentuais de estilo devem somar 100% (agora: ${shareSum.toFixed(1)}%).`);
      return;
    }

    setLoading(true);
    try {
      const body = {
        stars: starsNum,
        accuracy: accNum,
        share_acc: shareNums.share_acc / 100,
        share_tech: shareNums.share_tech / 100,
        share_speed: shareNums.share_speed / 100,
      };
      const [calcResult, gainResult] = await Promise.all([
        postJson<CalcResponse>("/calc", body),
        scoresPps.length > 0
          ? postJson<CalcGainResponse>("/calc/gain", {
              scores_pps: scoresPps,
              expected_pp: 1.0,
            })
          : Promise.resolve(null),
      ]);
      setCalc(calcResult);
      setGain(gainResult);
    } catch (cause) {
      setCalc(null);
      setGain(null);
      setError(
        cause instanceof ApiError
          ? `Falha ao calcular: ${cause.message}`
          : "Falha ao calcular. Verifique se o backend está no ar.",
      );
    } finally {
      setLoading(false);
    }
  }

  const breakdown: Array<{ key: SubComponentKey; value: number }> = calc
    ? [
        { key: "acc", value: calc.pp_acc },
        { key: "tech", value: calc.pp_tech },
        { key: "speed", value: calc.pp_speed },
      ]
    : [];

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_1fr_1.4fr]">
        <label className="flex flex-col gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Estrelas
          <input
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0.01"
            value={stars}
            onChange={(event) => setStars(event.target.value)}
            className={INPUT_CLASSES}
            aria-label="Total stars do mapa"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Accuracy (%)
          <input
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0.01"
            max="100"
            value={accuracy}
            onChange={(event) => setAccuracy(event.target.value)}
            className={INPUT_CLASSES}
            aria-label="Accuracy em porcentagem"
          />
        </label>
        <fieldset className="grid grid-cols-3 gap-2">
          <legend className="sr-only">Distribuição do estilo da dificuldade</legend>
          {SHARE_FIELDS.map((field) => (
            <label
              key={field.key}
              className="flex flex-col gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"
            >
              <span className={field.meta.text}>{field.label}</span>
              <input
                type="number"
                inputMode="decimal"
                step="1"
                min="0"
                max="100"
                value={shares[field.key]}
                onChange={(event) =>
                  setShares((current) => ({ ...current, [field.key]: event.target.value }))
                }
                className={INPUT_CLASSES}
              />
            </label>
          ))}
        </fieldset>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={loading}>
          {loading ? <Spinner size={14} /> : null}
          Calcular
        </Button>
        {error ? (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}
      </div>

      {calc ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border-subtle bg-background p-4">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">
              PP da jogada
            </span>
            <span className="text-3xl font-black tabular-nums text-accent">
              {formatPp(calc.pp_total)}
            </span>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm tabular-nums">
            {breakdown.map((part) => (
              <span key={part.key} className={COMPONENT_META[part.key].text}>
                {COMPONENT_META[part.key].label} {formatPp(part.value)}
              </span>
            ))}
          </div>
          {gain ? (
            <p className="border-t border-border-subtle pt-3 text-sm text-muted">
              Para ganhar <span className="font-bold text-foreground">+{formatPp(gain.expected_weighted_gain)} PP</span> ponderado,
              sua próxima jogada precisa valer{" "}
              <span className="font-bold text-secondary">
                ≈ {formatPp(gain.raw_pp_needed)} PP
              </span>{" "}
              cru (considerando seus {scoresPps.length} melhores scores).
            </p>
          ) : (
            <p className="border-t border-border-subtle pt-3 text-sm text-muted">
              Faça um score rankeado para estimar o ganho ponderado (+1pp).
            </p>
          )}
        </div>
      ) : null}
    </form>
  );
}
