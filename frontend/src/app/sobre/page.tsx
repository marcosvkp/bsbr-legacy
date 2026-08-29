import type { Metadata } from "next";
import { SobreWiki } from "./sobre-wiki";

export const metadata: Metadata = {
  title: "Sobre o sistema de PP",
  description:
    "Como o BSBR calcula o PP: stars das dificuldades, curva de acurácia, decomposição Acc/Tech/Speed e agregação ponderada do jogador.",
};

export default function SobrePage() {
  return <SobreWiki />;
}
