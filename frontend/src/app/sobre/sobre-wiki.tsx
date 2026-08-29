"use client";

import type { MouseEvent, ReactNode } from "react";
import { useMemo, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber } from "@/lib/format";

const DISCORD_URL = "https://discord.gg/HE5WERy6Ku";

// Pontos ilustrativos da curva (acc_fraction, multiplicador) — fonte curve.py
const CURVE_SAMPLE: Array<{ acc: string; mult: string }> = [
  { acc: "80,00%", mult: "0,69" },
  { acc: "90,00%", mult: "0,83" },
  { acc: "93,00%", mult: "0,90" },
  { acc: "95,00%", mult: "1,00" },
  { acc: "96,00%", mult: "1,09" },
  { acc: "97,00%", mult: "1,25" },
  { acc: "98,00%", mult: "1,57" },
  { acc: "99,00%", mult: "2,32" },
  { acc: "99,50%", mult: "5,02" },
  { acc: "100%", mult: "5,37" },
];

// Pontos de calibração exatos (acc 0.80 → 1.00) do backend (curve.py).
const CURVE_POINTS: Array<[number, number]> = [
  [0.8, 0.6872268862950283],
  [0.825, 0.7150465663454271],
  [0.85, 0.7462290664143185],
  [0.875, 0.7816934560296046],
  [0.9, 0.825756123560842],
  [0.91, 0.8488375988124467],
  [0.92, 0.8728710341448851],
  [0.93, 0.9039994071865736],
  [0.94, 0.9417362980580238],
  [0.95, 1.0],
  [0.955, 1.0388633331418984],
  [0.96, 1.0871883573850478],
  [0.965, 1.1552120359501035],
  [0.97, 1.2485807759957321],
  [0.9725, 1.3090333065057616],
  [0.975, 1.3807102743105126],
  [0.9775, 1.4664726399289512],
  [0.98, 1.5702410055532239],
  [0.9825, 1.697536248647543],
  [0.985, 1.8563887693647105],
  [0.9875, 2.058947159052738],
  [0.99, 2.324506282149922],
  [0.99125, 2.4902905794106913],
  [0.9925, 2.685667856592722],
  [0.99375, 2.9190155639254955],
  [0.995, 3.2022017597337955],
  [0.99625, 3.5526145337555373],
  [0.9975, 3.996793606763322],
  [0.99825, 4.325027383589547],
  [0.999, 4.715470646416203],
  [0.9995, 5.019543595874787],
  [1.0, 5.367394282890631],
];

function Formula({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border-subtle bg-background/60 px-3.5 py-3 font-mono text-[13px] leading-relaxed text-foreground">
      {children}
    </div>
  );
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[12px] font-semibold text-secondary">
      {children}
    </span>
  );
}

function CurveChart() {
  const X_MIN = 0.8;
  const X_MAX = 1.0;
  const Y_MAX = 5.6;
  const W = 640;
  const H = 320;
  const PAD = { top: 18, right: 72, bottom: 36, left: 44 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const x = (acc: number) => PAD.left + ((acc - X_MIN) / (X_MAX - X_MIN)) * plotW;
  const y = (mult: number) => PAD.top + (1 - mult / Y_MAX) * plotH;

  const linePoints = CURVE_POINTS.map(([acc, mult]) => `${x(acc)},${y(mult)}`).join(" ");
  const areaPath = [
    `M ${x(CURVE_POINTS[0][0])} ${y(0)}`,
    ...CURVE_POINTS.map(([acc, mult]) => `L ${x(acc)} ${y(mult)}`),
    `L ${x(CURVE_POINTS[CURVE_POINTS.length - 1][0])} ${y(0)}`,
    "Z",
  ].join(" ");

  const fmt = (value: number) => value.toFixed(2).replace(".", ",");
  const yTicks = [0, 1, 2, 3, 4, 5];
  const xTicks = [0.8, 0.85, 0.9, 0.95, 1.0];
  const marker95 = CURVE_POINTS.find(([acc]) => acc === 0.95)!;
  const marker100 = CURVE_POINTS[CURVE_POINTS.length - 1];

  return (
    <div className="overflow-hidden rounded-lg border border-border-subtle bg-background/40">
      <svg
        role="img"
        aria-label="Gráfico do multiplicador de PP por acurácia, de 80% a 100%"
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxWidth: 640 }}
      >
        <defs>
          <linearGradient id="curve-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--secondary)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--secondary)" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Grid horizontal */}
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              y1={y(tick)}
              x2={W - PAD.right}
              y2={y(tick)}
              stroke="var(--border)"
              strokeWidth={1}
              strokeDasharray={tick === 0 ? undefined : "3 4"}
            />
            <text
              x={PAD.left - 7}
              y={y(tick) + 3.5}
              textAnchor="end"
              fontSize={11}
              fill="var(--muted)"
            >
              {fmt(tick)}
            </text>
          </g>
        ))}

        {/* Grid vertical */}
        {xTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={x(tick)}
              y1={PAD.top}
              x2={x(tick)}
              y2={H - PAD.bottom}
              stroke="var(--border)"
              strokeWidth={1}
              strokeDasharray="3 4"
            />
            <text
              x={x(tick)}
              y={H - PAD.bottom + 16}
              textAnchor="middle"
              fontSize={11}
              fill="var(--muted)"
            >
              {tick === 1 ? "100%" : `${Math.round(tick * 100)}%`}
            </text>
          </g>
        ))}

        {/* Área + linha da curva */}
        <path d={areaPath} fill="url(#curve-fill)" />
        <polyline
          points={linePoints}
          fill="none"
          stroke="var(--secondary)"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Marcos 95% e 100% */}
        <circle cx={x(marker95[0])} cy={y(marker95[1])} r={4} fill="var(--accent)" />
        <text
          x={x(marker95[0])}
          y={y(marker95[1]) - 9}
          textAnchor="middle"
          fontSize={11}
          fontWeight={700}
          fill="var(--accent)"
        >
          95% = 1,00
        </text>
        <circle cx={x(marker100[0])} cy={y(marker100[1])} r={4} fill="var(--accent)" />
        <text
          x={x(marker100[0])}
          y={y(marker100[1]) + 16}
          textAnchor="middle"
          fontSize={11}
          fontWeight={700}
          fill="var(--accent)"
        >
          100% = 5,37
        </text>

        {/* Eixos */}
        <text
          x={PAD.left - 32}
          y={PAD.top + plotH / 2}
          transform={`rotate(-90 ${PAD.left - 32} ${PAD.top + plotH / 2})`}
          textAnchor="middle"
          fontSize={11}
          fontWeight={600}
          fill="var(--muted)"
        >
          Multiplicador
        </text>
        <text
          x={PAD.left + plotW / 2}
          y={H - 6}
          textAnchor="middle"
          fontSize={11}
          fontWeight={600}
          fill="var(--muted)"
        >
          Acurácia
        </text>
      </svg>
    </div>
  );
}

function StarsSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>1 · Stars das dificuldades</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm leading-relaxed text-muted">
        <p>
          Cada dificuldade rankeada recebe uma nota de dificuldade em <Kbd>stars</Kbd> — o total
          de estrelas do mapa. Esse total é decomposto em três{" "}
          <strong className="text-foreground">sub-stars</strong>, que definem o peso de cada
          estilo naquela dificuldade:
        </p>
        <div className="grid gap-2 sm:grid-cols-3">
          {[
            { label: "Acc", desc: "exigência de precisão", cls: "text-secondary", cell: "bg-secondary/10 border-secondary/25" },
            { label: "Tech", desc: "padrões técnicos", cls: "text-accent", cell: "bg-accent/10 border-accent/25" },
            { label: "Speed", desc: "velocidade/streams", cls: "text-success", cell: "bg-success/10 border-success/25" },
          ].map((item) => (
            <div key={item.label} className={`rounded-lg border px-3 py-2.5 ${item.cell}`}>
              <p className={`text-sm font-black uppercase tracking-widest ${item.cls}`}>{item.label}</p>
              <p className="mt-0.5 text-xs text-muted">{item.desc}</p>
            </div>
          ))}
        </div>
        <p>
          Exemplo: uma dificuldade de <Kbd>8,74★</Kbd> pode ter{" "}
          <Kbd>2,90 acc</Kbd> + <Kbd>2,17 tech</Kbd> + <Kbd>3,67 speed</Kbd>. As shares são
          usadas para decompor o PP do score (seção 3).
        </p>
      </CardContent>
    </Card>
  );
}

function CurvaSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>2 · A curva de PP</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm leading-relaxed text-muted">
        <p>
          O PP bruto de um score é o produto das estrelas por um multiplicador que depende da
          acurácia:
        </p>
        <Formula>
          <span className="text-secondary">PP</span> = stars × 42,117208413 ×{" "}
          <span className="text-accent">mod(acc)</span>
        </Formula>
        <p>
          O multiplicador <Kbd>mod(acc)</Kbd> vem de uma curva <em>piecewise-linear</em> com{" "}
          <strong className="text-foreground">36 pontos de calibração</strong>, portada do legado
          do BSBR. Em <Kbd>95%</Kbd> de acurácia o multiplicador é exatamente{" "}
          <Kbd>1,00</Kbd> (ponto de referência) e cresce de forma explosiva perto de{" "}
          <Kbd>100%</Kbd> — até <Kbd>5,37</Kbd>:
        </p>
        <CurveChart />
        <div className="overflow-hidden rounded-lg border border-border-subtle">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle bg-background/50 text-left text-[11px] uppercase tracking-wider text-muted">
                <th scope="col" className="px-3.5 py-2 font-bold">Acurácia</th>
                <th scope="col" className="px-3.5 py-2 text-right font-bold">Multiplicador</th>
                <th scope="col" className="hidden px-3.5 py-2 text-right font-bold sm:table-cell">PP em 8,5★</th>
              </tr>
            </thead>
            <tbody>
              {CURVE_SAMPLE.map((row) => (
                <tr key={row.acc} className="border-b border-border-subtle/50 last:border-b-0">
                  <td className="px-3.5 py-1.5 tabular-nums">{row.acc}</td>
                  <td className="px-3.5 py-1.5 text-right font-bold tabular-nums text-secondary">
                    {row.mult}
                  </td>
                  <td className="hidden px-3.5 py-1.5 text-right tabular-nums sm:table-cell">
                    {formatNumber(8.5 * 42.117208413 * parseFloat(row.mult.replace(",", ".")))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Repare no salto: a diferença entre 97% e 99% multiplica o PP por quase 2×, e entre 99% e
          100% por mais 2,3×. É por isso que um “full combo” com acc altíssima vale muito mais que
          a mesma nota com acc mediana.
        </p>
      </CardContent>
    </Card>
  );
}

function DecomposicaoSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>3 · Decomposição Acc / Tech / Speed</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm leading-relaxed text-muted">
        <p>
          Os sub-PPs não são uma fórmula nova: são uma{" "}
          <strong className="text-foreground">divisão do PP total</strong> proporcional aos
          sub-stars do mapa, com um ajuste de sensibilidade à acurácia. Cada estilo tem sua
          própria “g”:
        </p>
        <Formula>
          g_acc(acc)   = mod(acc) / mod(0,95)<br />
          g_tech(acc)  = e<sup>1,9 × (acc − 0,95)</sup><br />
          g_speed(acc) = e<sup>1,2 × (acc − 0,95)</sup><br />
          <br />
          subPP_x = totalPP × <span className="text-secondary">share_x</span> × g_x(acc) / Σ(share × g)
        </Formula>
        <p>
          A soma é normalizada, então sempre vale{" "}
          <Kbd>pp_acc + pp_tech + pp_speed = pp_total</Kbd>. Em <Kbd>95%</Kbd> de acc as três
          funções valem 1,0 e o sub-PP sai exatamente proporcional aos shares. Acima disso, a
          sensibilidade da tech (<Kbd>1,9</Kbd>) cresce mais rápido que a da speed (<Kbd>1,2</Kbd>) —
          mapas técnicos são mais generosos com quem fecha acc muito alta.
        </p>
      </CardContent>
    </Card>
  );
}

function AgregacaoSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>4 · PP do jogador</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm leading-relaxed text-muted">
        <p>
          O PP exibido no perfil é a <strong className="text-foreground">soma ponderada</strong>{" "}
          dos PP de todos os scores em mapas <Kbd>RANKED</Kbd>, ordenados do maior para o menor:
        </p>
        <Formula>
          PP_jogador = Σ pp<sub>i</sub> × 0,965<sup>i</sup>
        </Formula>
        <p>
          O melhor score vale <Kbd>100%</Kbd>, o segundo <Kbd>96,5%</Kbd>, o terceiro{" "}
          <Kbd>93,1%</Kbd> e assim por diante. Ou seja: consistência importa, mas os melhores
          scores dominam o total — bater um recorde próprio em um mapa difícil vale mais do que
          encher a conta de scores medianos.
        </p>
      </CardContent>
    </Card>
  );
}

function DiscordSection() {
  return (
    <Card>
      <CardContent className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <h2 className="font-display text-xl font-extrabold uppercase tracking-tight">
            Participe do servidor
          </h2>
          <p className="text-sm text-muted">
            Dúvidas sobre o ranking, sugestões de mapas e a comunidade BR de Beat Saber.
          </p>
        </div>
        <Link
          href={DISCORD_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-2.5 rounded-lg border border-accent/50 bg-accent/15 px-5 py-2.5 font-bold text-white shadow-[0_0_16px_var(--glow-accent)] transition-transform hover:-translate-y-0.5"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5">
            <path d="M20.32 4.37a19.8 19.8 0 0 0-4.93-1.51 13.8 13.8 0 0 0-.64 1.28 18.3 18.3 0 0 0-5.5 0 13.8 13.8 0 0 0-.64-1.28c-1.71.29-3.37.8-4.93 1.51A20.3 20.3 0 0 0 .1 18.06a19.9 19.9 0 0 0 6.07 3.06 14.8 14.8 0 0 0 1.3-2.1 12.8 12.8 0 0 1-2.05-.98l.5-.39a14.2 14.2 0 0 0 12.16 0l.5.39c-.65.4-1.34.73-2.05.98.38.74.82 1.44 1.3 2.1a19.9 19.9 0 0 0 6.07-3.06 20.3 20.3 0 0 0-3.58-13.69ZM8.68 15.34c-1.18 0-2.15-1.08-2.15-2.42 0-1.33.95-2.42 2.15-2.42 1.2 0 2.17 1.09 2.15 2.42 0 1.34-.95 2.42-2.15 2.42Zm6.64 0c-1.18 0-2.15-1.08-2.15-2.42 0-1.33.95-2.42 2.15-2.42 1.2 0 2.17 1.09 2.15 2.42 0 1.34-.94 2.42-2.15 2.42Z" />
          </svg>
          Entrar no Discord
        </Link>
      </CardContent>
    </Card>
  );
}

interface Section {
  id: string;
  title: string;
  keywords: string;
  node: ReactNode;
}

const SECTIONS: Section[] = [
  {
    id: "stars",
    title: "1 · Stars das dificuldades",
    keywords: "stars estrelas dificuldade acc tech speed sub-stars nota share",
    node: <StarsSection />,
  },
  {
    id: "curva",
    title: "2 · A curva de PP",
    keywords: "curva pp multiplicador acurácia mod gráfico calibração 36 pontos 95 100",
    node: <CurvaSection />,
  },
  {
    id: "decomposicao",
    title: "3 · Decomposição Acc / Tech / Speed",
    keywords: "decomposição sub-pp share g_acc g_tech g_speed sensibilidade fórmula pp_total",
    node: <DecomposicaoSection />,
  },
  {
    id: "agregacao",
    title: "4 · PP do jogador",
    keywords: "agregação ponderação peso soma 0,965 scores melhores consistência recorde",
    node: <AgregacaoSection />,
  },
  {
    id: "discord",
    title: "Participe do servidor",
    keywords: "discord servidor comunidade dúvidas sugestões contato",
    node: <DiscordSection />,
  },
];

const normalize = (value: string) =>
  value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

function scrollToSection(id: string) {
  return (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    history.replaceState(null, "", `#${id}`);
  };
}

export function SobreWiki() {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = normalize(query.trim());
    if (!q) return SECTIONS;
    return SECTIONS.filter((section) =>
      normalize(`${section.title} ${section.keywords}`).includes(q),
    );
  }, [query]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold uppercase tracking-tight">
            Como funciona o <span className="text-secondary">PP</span>
          </h1>
          <p className="mt-1 text-sm text-muted">
            O PP (performance points) mede o desempenho dos jogadores nos mapas rankeados do
            ranking brasileiro de Beat Saber. O motor é um porte exato da curva do ranking legado
            do BSBR, com decomposição de estilo (Acc/Tech/Speed) herdada do BeatLeader.
          </p>
        </div>
        <label className="relative flex max-w-md items-center">
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="pointer-events-none absolute left-3 h-4 w-4 text-muted"
          >
            <path
              fillRule="evenodd"
              d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
              clipRule="evenodd"
            />
          </svg>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar tópico… (ex.: curva, decomposição, speed)"
            aria-label="Buscar tópico"
            className="h-9 w-full rounded-md border border-border-subtle bg-surface pl-9 pr-3 text-sm text-foreground placeholder:text-muted focus:border-secondary focus:outline-none"
          />
        </label>
      </div>

      <div className="lg:grid lg:grid-cols-[230px_1fr] lg:gap-8">
        <aside className="hidden lg:block">
          <nav aria-label="Tópicos" className="sticky top-20 flex flex-col gap-2">
            <p className="text-[11px] font-bold uppercase tracking-widest text-muted">Tópicos</p>
            <ul className="flex flex-col gap-1">
              {filtered.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    onClick={scrollToSection(section.id)}
                    className="block rounded-md px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-surface hover:text-foreground"
                  >
                    {section.title}
                  </a>
                </li>
              ))}
              {filtered.length === 0 ? (
                <li className="px-2.5 py-1.5 text-sm text-muted/60">Nenhum tópico encontrado</li>
              ) : null}
            </ul>
          </nav>
        </aside>

        <main className="flex min-w-0 flex-col gap-6">
          {filtered.length === 0 ? (
            <div className="rounded-xl border border-border-subtle bg-surface px-4 py-10 text-center">
              <p className="text-sm font-semibold text-foreground">Nenhum tópico encontrado</p>
              <p className="mt-1 text-sm text-muted">
                Tente buscar por “curva”, “stars”, “decomposição”, “ponderada” ou “discord”.
              </p>
            </div>
          ) : (
            filtered.map((section) => (
              <section key={section.id} id={section.id} className="scroll-mt-24">
                {section.node}
              </section>
            ))
          )}
        </main>
      </div>
    </div>
  );
}
