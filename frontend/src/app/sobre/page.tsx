import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber } from "@/lib/format";

export const metadata: Metadata = {
  title: "Sobre o sistema de PP",
  description:
    "Como o BSBR calcula o PP: stars das dificuldades, curva de acurácia, decomposição Acc/Tech/Speed e agregação ponderada do jogador.",
};

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

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border-subtle bg-background/60 px-3.5 py-3 font-mono text-[13px] leading-relaxed text-foreground">
      {children}
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[12px] font-semibold text-secondary">
      {children}
    </span>
  );
}

export default function SobrePage() {
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="font-display text-3xl font-extrabold uppercase tracking-tight">
          Como funciona o <span className="text-secondary">PP</span>
        </h1>
        <p className="mt-1 text-sm text-muted">
          O PP (performance points) mede o desempenho dos jogadores nos mapas rankeados do
          ranking brasileiro de Beat Saber. O motor é um porte exato da curva do ranking
          legado do BSBR, com decomposição de estilo (Acc/Tech/Speed) herdada do BeatLeader.
        </p>
      </div>

      {/* 1. Stars */}
      <Card>
        <CardHeader>
          <CardTitle>1 · Stars das dificuldades</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm leading-relaxed text-muted">
          <p>
            Cada dificuldade rankeada recebe uma nota de dificuldade em <Kbd>stars</Kbd> —
            o total de estrelas do mapa. Esse total é decomposto em três{" "}
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

      {/* 2. Curva */}
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
            <strong className="text-foreground">36 pontos de calibração</strong>, portada do
            legado do BSBR. Em <Kbd>95%</Kbd> de acurácia o multiplicador é exatamente{" "}
            <Kbd>1,00</Kbd> (ponto de referência) e cresce de forma explosiva perto de{" "}
            <Kbd>100%</Kbd> — até <Kbd>5,37</Kbd>:
          </p>
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
            Repare no salto: a diferença entre 97% e 99% multiplica o PP por quase 2×, e entre
            99% e 100% por mais 2,3×. É por isso que um “full combo” com acc altíssima vale
            muito mais que a mesma nota com acc mediana.
          </p>
        </CardContent>
      </Card>

      {/* 3. Decomposição */}
      <Card>
        <CardHeader>
          <CardTitle>3 · Decomposição Acc / Tech / Speed</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm leading-relaxed text-muted">
          <p>
            Os sub-PPs não são uma fórmula nova: são uma <strong className="text-foreground">
            divisão do PP total</strong> proporcional aos sub-stars do mapa, com um ajuste de
            sensibilidade à acurácia. Cada estilo tem sua própria “g”:
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

      {/* 4. Agregação */}
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

      {/* Discord */}
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
    </div>
  );
}
