import { redirect } from "next/navigation";

/** A lista de jogadores é o próprio ranking. */
export default function JogadoresIndexPage() {
  redirect("/ranking");
}
