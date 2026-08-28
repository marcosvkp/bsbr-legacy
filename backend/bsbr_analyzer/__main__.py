"""
CLI do bsbr_analyzer.

Comandos:
  analyze         Analisa um mapa do BeatSaver (id ou hash) e imprime o rating
  download        Baixa mapas rankeados do ScoreSaber e constroi o dataset de treino
  train           Treina o modelo de predicao de stars (data/dataset.csv -> models/)
  dataset-info    Mostra estatisticas do dataset atual
"""

from __future__ import annotations

import argparse
import sys

from .analysis import analyze_map


def cmd_analyze(args) -> int:
    analysis = analyze_map(args.source)

    print(f"\n{analysis.name}  ?  mapper: {analysis.mapper}  ?  BPM: {analysis.bpm:g}")
    header = (
        f"{'Diff':<12} {'NJS':>5} {'Notas':>6} {'NPS':>6} "
        f"{'Total':>7} {'Acc':>6} {'Tech':>6} {'Speed':>6}  Estilo"
    )
    print(header)
    print("-" * len(header))
    for d in analysis.difficulties:
        print(
            f"{d.difficulty:<12} {d.njs:>5.1f} {d.notes:>6} {d.nps:>6.2f} "
            f"{d.total_stars:>6.2f}* {d.acc_stars:>5.2f} {d.tech_stars:>5.2f} "
            f"{d.speed_stars:>5.2f}  {', '.join(d.style_tags)}  [{d.stars_source}]"
        )
    if not analysis.difficulties:
        print("(nenhuma dificuldade Standard analisavel)")
        return 1
    return 0


def cmd_download(args) -> int:
    from .dataset import cmd_download as _cmd_download

    _cmd_download(limit=args.limit, threads=args.threads, force=args.force)
    return 0


def cmd_train(args) -> int:
    from .trainer import train_model

    metrics = train_model()
    print(
        f"\nTreino concluido: {metrics['n_samples']} amostras, "
        f"MAE CV {metrics['mae_cv']:.4f} +-{metrics['mae_cv_std']:.4f}, "
        f"R^2 CV {metrics['r2_cv']:.4f}"
    )
    return 0


def cmd_dataset_info(args) -> int:
    from .dataset import dataset_stats

    stats = dataset_stats()
    if not stats.get("rows"):
        print("dataset.csv nao encontrado. Rode 'download' primeiro.")
        return 1
    print(f"\nDataset: {stats['rows']} linhas | {stats['unique_maps']} musicas unicas")
    for diff, count in sorted(stats["by_difficulty"].items()):
        print(f"  {diff:<12} : {count}")
    return 0


def main(argv=None) -> int:
    # Console Windows (cp1252): caracteres fora do mapa (ex.: nomes de musica
    # com Unicode raro) viram "?" em vez de crashar o print.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    argv = list(sys.argv[1:] if argv is None else argv)
    # Compat: `python -m bsbr_analyzer <source>` e tratado como `analyze`
    if argv and argv[0] not in ("analyze", "download", "train", "dataset-info"):
        argv = ["analyze"] + argv

    parser = argparse.ArgumentParser(
        prog="bsbr_analyzer",
        description="Analyzer e ML de rating do BSBR (parity com BSStarAnalyzer).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_an = sub.add_parser("analyze", help="Analisa um mapa do BeatSaver (id ou hash)")
    p_an.add_argument("source", help="map_id ou hash (40 hex) do BeatSaver")
    p_an.set_defaults(func=cmd_analyze)

    p_dl = sub.add_parser("download", help="Constroi o dataset de treino (ScoreSaber -> BeatSaver)")
    p_dl.add_argument("--limit", type=int, default=500,
                      help="Numero de dificuldades rankeadas para buscar (padrao: 500)")
    p_dl.add_argument("--threads", type=int, default=4,
                      help="Threads paralelas para download/analise (padrao: 4)")
    p_dl.add_argument("--force", action="store_true",
                      help="Reprocessa entradas ja presentes no dataset")
    p_dl.set_defaults(func=cmd_download)

    p_tr = sub.add_parser("train", help="Treina o modelo de predicao de stars")
    p_tr.set_defaults(func=cmd_train)

    p_di = sub.add_parser("dataset-info", help="Mostra estatisticas do dataset atual")
    p_di.set_defaults(func=cmd_dataset_info)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
