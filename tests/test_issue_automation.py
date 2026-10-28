#!/usr/bin/env python3
"""Project Nox Requests - Automation Logic Unit & Edge Case Test Suite
Simulates the GitHub Actions JavaScript workflow logic for:
1. Title normalization (prevent duplicates, extract clean titles, format prefixes)
2. Type classification (Mangá vs Anime mutual exclusivity)
3. Category classification (Nova extensão, Problema na extensão, etc.)
4. NSFW +18 classification (Sim -> add, Não -> remove)
5. Initial status (Em análise)
6. Idempotence on multiple executions and edits
7. Validation of the new compact templates structure and empty defaults
"""

import os
import re
import unittest
import yaml

def simulate_workflow(issue_title, issue_body, current_labels, is_closed=False):
    title = issue_title.strip()
    body = issue_body or ""
    labels = set(current_labels)
    labels_to_add = set()
    labels_to_remove = set()

    # 1. Determine category
    category = None
    if any(l in labels for l in ["Nova extensão"]):
        category = "Nova extensão"
    elif any(l in labels for l in ["Problema na extensão", "Bug"]):
        category = "Problema na extensão"
    elif any(l in labels for l in ["Mudança de domínio"]):
        category = "Mudança de domínio"
    elif any(l in labels for l in ["Fonte indisponível", "Fonte morta"]):
        category = "Fonte indisponível"
    elif any(l in labels for l in ["Sugestão"]):
        category = "Sugestão"
    else:
        # Fallback heuristic from body inspection
        if "Qual extensão está apresentando o problema?" in body or "Parte afetada" in body:
            category = "Problema na extensão"
        elif ("URL oficial do site" in body or "URL do site" in body) and ("Precisa de login?" in body or "Precisa de VIP" in body):
            category = "Nova extensão"
        elif "Domínio ou URL antigo" in body or "URL antiga" in body:
            category = "Mudança de domínio"
        elif "O que aconteceu com a fonte?" in body or "O que aconteceu?" in body:
            category = "Fonte indisponível"
        elif "Proposta de melhoria" in body or "Título ou resumo" in body or "Descrição da melhoria" in body:
            category = "Sugestão"

    # --- Title Normalization ---
    # Strip any existing prefix (supports multiple/duplicate prefixes)
    prefix_pattern = r'^\s*(\[(?:Nova extensão|Problema na extensão|Bug|Mudança de domínio|Fonte indisponível|Fonte morta|Sugestão)\]\s*:\s*)+'
    clean_title = re.sub(prefix_pattern, '', title, flags=re.IGNORECASE).strip()

    def extract_field(pattern):
        m = re.search(pattern, body, flags=re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""

    desired_title = title
    if category == "Nova extensão":
        fonte_name = extract_field(r'###\s*Nome d[oa] (?:fonte\/site|fonte|site)\s*\r?\n+([^\r\n#]+)')
        final_name = fonte_name or clean_title or "Nova fonte"
        desired_title = f"[Nova extensão]: {final_name}"

    elif category == "Problema na extensão":
        ext_name = extract_field(r'###\s*(?:Qual extensão está apresentando o problema\?|Nome da extensão)\s*\r?\n+([^\r\n#]+)')
        if ext_name:
            ext_prefix_re = re.compile(rf'^{re.escape(ext_name)}\s*[-—:]\s*', re.IGNORECASE)
            if ext_prefix_re.search(clean_title):
                summary = ext_prefix_re.sub('', clean_title).strip()
                desired_title = f"[Problema na extensão]: {ext_name} — {summary}" if summary else f"[Problema na extensão]: {ext_name}"
            elif clean_title.lower() == ext_name.lower() or not clean_title:
                desired_title = f"[Problema na extensão]: {ext_name}"
            else:
                desired_title = f"[Problema na extensão]: {ext_name} — {clean_title}"
        else:
            desired_title = f"[Problema na extensão]: {clean_title or 'Problema relatado'}"

    elif category == "Mudança de domínio":
        ext_name = extract_field(r'###\s*Nome da extensão\s*\r?\n+([^\r\n#]+)')
        final_name = ext_name or clean_title or "Extensão"
        desired_title = f"[Mudança de domínio]: {final_name}"

    elif category == "Fonte indisponível":
        ext_name = extract_field(r'###\s*Nome da extensão\s*\r?\n+([^\r\n#]+)')
        final_name = ext_name or clean_title or "Extensão"
        desired_title = f"[Fonte indisponível]: {final_name}"

    elif category == "Sugestão":
        summary = extract_field(r'###\s*Título ou resumo(?: da sugestão)?\s*\r?\n+([^\r\n#]+)')
        final_summary = clean_title or summary or "Sugestão"
        desired_title = f"[Sugestão]: {final_summary}"

    # Clean double dashes or spaces
    desired_title = re.sub(r'\s*—\s*—\s*', ' — ', desired_title).strip()

    # --- Type Classification ---
    type_match = re.search(r'###\s*Tipo(?: de extensão)?(?:[^\r\n]*)?\r?\n+\s*(Mangá|Anime)\s*$', body, flags=re.IGNORECASE | re.MULTILINE)
    if type_match:
        selected_type = "Mangá" if "mang" in type_match.group(1).lower() else "Anime"
        opposite_type = "Anime" if selected_type == "Mangá" else "Mangá"
        legacy_opposites = ["Anime", "type:anime"] if selected_type == "Mangá" else ["Manga", "Mangá", "type:manga"]

        if selected_type not in labels:
            labels_to_add.add(selected_type)

        for rem in [opposite_type] + legacy_opposites:
            if rem != selected_type and rem in labels:
                labels_to_remove.add(rem)

    # --- NSFW Classification ---
    nsfw_match = re.search(r'###\s*(?:O site possui conteúdo \+18\?|Conteúdo \+18\??)(?:[^\r\n]*)?\r?\n+\s*(Sim|Não)', body, flags=re.IGNORECASE | re.MULTILINE)
    if nsfw_match:
        val = nsfw_match.group(1).lower()
        if "sim" in val:
            if "Conteúdo +18" not in labels:
                labels_to_add.add("Conteúdo +18")
            if "+18" in labels:
                labels_to_remove.add("+18")
        else:
            if "Conteúdo +18" in labels:
                labels_to_remove.add("Conteúdo +18")
            if "+18" in labels:
                labels_to_remove.add("+18")

    # --- Category Label Ensure ---
    if category and category not in labels:
        labels_to_add.add(category)

    # Remove legacy category equivalents
    if category == "Problema na extensão" and "Bug" in labels:
        labels_to_remove.add("Bug")
    if category == "Fonte indisponível" and "Fonte morta" in labels:
        labels_to_remove.add("Fonte morta")

    # --- Initial Status ---
    statuses = {"Em análise", "Aceito", "Em desenvolvimento", "Aguardando informações"}
    resolutions = {"Concluído", "Recusado", "Duplicado", "Cancelado"}
    has_status = any(l in statuses or l.startswith("status:") for l in labels.union(labels_to_add))
    has_res = any(l in resolutions or l.startswith("resolution:") for l in labels.union(labels_to_add))

    if not is_closed and not has_status and not has_res:
        labels_to_add.add("Em análise")

    final_labels = (labels.union(labels_to_add)) - labels_to_remove

    return {
        "title": desired_title,
        "labels_to_add": sorted(list(labels_to_add)),
        "labels_to_remove": sorted(list(labels_to_remove)),
        "final_labels": sorted(list(final_labels))
    }


class TestIssueAutomation(unittest.TestCase):
    TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.github/ISSUE_TEMPLATE"))

    def test_nova_extensao_new_compact_template(self):
        body = """### Tipo de extensão
Mangá
### Nome da fonte
SukiMangas
### URL do site
https://sukimangas.com
### Idioma
Português (Brasil)
### Precisa de login?
Não
### Precisa de VIP/Premium?
Não
### Conteúdo +18?
Não
### Observações (opcional)
Site muito rápido e atualizado.
"""
        res = simulate_workflow("SukiMangas", body, ["Nova extensão"])
        self.assertEqual(res["title"], "[Nova extensão]: SukiMangas")
        self.assertIn("Mangá", res["final_labels"])
        self.assertIn("Nova extensão", res["final_labels"])
        self.assertIn("Em análise", res["final_labels"])
        self.assertNotIn("Conteúdo +18", res["final_labels"])

    def test_nova_extensao_with_nsfw_anime_new_compact(self):
        body = """### Tipo de extensão
Anime
### Nome da fonte
AnimeHentaiZone
### URL do site
https://hentaizone.example
### Idioma
Português (Brasil)
### Precisa de login?
Sim
### Precisa de VIP/Premium?
Parcialmente
### Conteúdo +18?
Sim
"""
        res = simulate_workflow("AnimeHentaiZone", body, ["Nova extensão"])
        self.assertEqual(res["title"], "[Nova extensão]: AnimeHentaiZone")
        self.assertIn("Anime", res["final_labels"])
        self.assertIn("Conteúdo +18", res["final_labels"])
        self.assertNotIn("Mangá", res["final_labels"])

    def test_nova_extensao_legacy_backward_compatibility(self):
        body = """### 📌 Informações da extensão
### Tipo de extensão
Mangá
### Nome da fonte/site
MangaLivre.lat
### URL oficial do site
https://mangalivre.lat
### O site possui conteúdo +18?
Não
"""
        res = simulate_workflow("MangaLivre.lat", body, ["Nova extensão"])
        self.assertEqual(res["title"], "[Nova extensão]: MangaLivre.lat")
        self.assertIn("Mangá", res["final_labels"])

    def test_bug_report_required_scenario(self):
        """Case from user specification:
        Extensão: MangaLivre.lat
        Versão: 1.6.60
        Aplicativo: Mihon
        Parte afetada: Leitor / Imagens
        Problema: Algumas páginas não carregam.
        """
        body = """### Tipo de extensão
Mangá
### Nome da extensão
MangaLivre.lat
### Versão da extensão
1.6.60
### Aplicativo utilizado
Mihon
### Parte afetada
Leitor / Imagens
### O que está acontecendo?
Algumas páginas não carregam ao abrir o capítulo.
### Como reproduzir?
Abrir a extensão MangaLivre.lat -> escolher obra -> ler capítulo.
### Informações complementares (opcional)
Ocorre tanto no Wi-Fi quanto no 4G.
"""
        # User sets natural title: "Algumas páginas não carregam"
        res = simulate_workflow("Algumas páginas não carregam", body, ["Problema na extensão"])
        self.assertEqual(res["title"], "[Problema na extensão]: MangaLivre.lat — Algumas páginas não carregam")
        self.assertIn("Mangá", res["final_labels"])
        self.assertIn("Problema na extensão", res["final_labels"])
        self.assertIn("Em análise", res["final_labels"])

    def test_bug_report_clean_extension_only_title(self):
        body = """### Tipo de extensão
Mangá
### Nome da extensão
MangaLivre.lat
### Versão da extensão
1.6.60
### Aplicativo utilizado
Mihon
### Parte afetada
Leitor / Imagens
### O que está acontecendo?
Algumas páginas não carregam.
### Como reproduzir?
Abrir capítulo 10.
"""
        # User just typed extension name in title
        res = simulate_workflow("MangaLivre.lat", body, ["Problema na extensão"])
        self.assertEqual(res["title"], "[Problema na extensão]: MangaLivre.lat")
        self.assertIn("Mangá", res["final_labels"])

    def test_domain_change_new_compact(self):
        body = """### Tipo de extensão
Anime
### Nome da extensão
BetterAnime
### URL antiga
https://antigo.betteranime.net
### URL nova
https://novo.betteranime.net
### Observações (opcional)
Mudança anunciada no canal do Telegram oficial.
"""
        res = simulate_workflow("BetterAnime mudou de domínio", body, ["Mudança de domínio"])
        self.assertEqual(res["title"], "[Mudança de domínio]: BetterAnime")
        self.assertIn("Anime", res["final_labels"])
        self.assertIn("Mudança de domínio", res["final_labels"])
        self.assertIn("Em análise", res["final_labels"])

    def test_dead_source_new_compact(self):
        body = """### Tipo de extensão
Mangá
### Nome da extensão
GoldenMangas
### O que aconteceu?
O domínio expirou há 3 semanas e a equipe confirmou encerramento definitivo no Discord.
### Informações complementares (opcional)
DNS NXDOMAIN.
"""
        res = simulate_workflow("GoldenMangas encerrou", body, ["Fonte indisponível"])
        self.assertEqual(res["title"], "[Fonte indisponível]: GoldenMangas")
        self.assertIn("Mangá", res["final_labels"])
        self.assertIn("Fonte indisponível", res["final_labels"])
        self.assertIn("Em análise", res["final_labels"])

    def test_feature_request_new_compact(self):
        body = """### Título ou resumo
Adicionar suporte a filtro por ano de lançamento no catálogo
### Descrição da melhoria
Permitir que os leitores filtrem obras por ano de publicação, facilitando encontrar clássicos ou lançamentos específicos.
### Extensão relacionada (opcional)

### Informações complementares (opcional)
Recurso já existente no leitor TachiyomiSY.
"""
        res = simulate_workflow("Filtro por ano de lançamento", body, ["Sugestão"])
        self.assertEqual(res["title"], "[Sugestão]: Filtro por ano de lançamento")
        self.assertIn("Sugestão", res["final_labels"])
        self.assertIn("Em análise", res["final_labels"])
        # Notice: general feature request does not force Mangá or Anime label!
        self.assertNotIn("Mangá", res["final_labels"])
        self.assertNotIn("Anime", res["final_labels"])

    def test_prevent_duplicate_prefixes_and_idempotence(self):
        body = """### Tipo de extensão
Mangá
### Nome da fonte
MangaLivre.lat
"""
        res1 = simulate_workflow("[Nova extensão]: MangaLivre.lat", body, ["Nova extensão", "Mangá", "Em análise"])
        self.assertEqual(res1["title"], "[Nova extensão]: MangaLivre.lat")
        self.assertEqual(len(res1["labels_to_add"]), 0)
        self.assertEqual(len(res1["labels_to_remove"]), 0)

        res2 = simulate_workflow("[Nova extensão]: [Nova extensão]: MangaLivre.lat", body, ["Nova extensão", "Mangá"])
        self.assertEqual(res2["title"], "[Nova extensão]: MangaLivre.lat")

    def test_edit_type_from_manga_to_anime(self):
        body = """### Tipo de extensão
Anime
### Nome da fonte
AnimeFire
"""
        res = simulate_workflow("AnimeFire", body, ["Nova extensão", "Mangá", "Em análise"])
        self.assertIn("Anime", res["final_labels"])
        self.assertNotIn("Mangá", res["final_labels"])
        self.assertIn("Mangá", res["labels_to_remove"])

    def test_edit_nsfw_from_sim_to_nao(self):
        body = """### Tipo de extensão
Mangá
### Nome da fonte
SukiMangas
### Conteúdo +18?
Não
"""
        res = simulate_workflow("SukiMangas", body, ["Nova extensão", "Mangá", "Conteúdo +18"])
        self.assertNotIn("Conteúdo +18", res["final_labels"])
        self.assertIn("Conteúdo +18", res["labels_to_remove"])

    # -------------------------------------------------------------------------
    # YAML Structure & Empty Defaults Tests
    # -------------------------------------------------------------------------
    def test_yaml_files_structure_and_constraints(self):
        """Verifies template constraints:
        - 01: 8 items, no repetitive checkboxes
        - 02: 8 items, version starts empty, app text starts empty, single dropdown for affected parts
        - 03: 5 items, no extension version
        - 04: 4 items, no giant warning markdown block
        - 05: 4 items, purpose consolidated into description
        """
        # 01_request_extension.yml
        path_01 = os.path.join(self.TEMPLATES_DIR, "01_request_extension.yml")
        with open(path_01, "r", encoding="utf-8") as f:
            t1 = yaml.safe_load(f)
        self.assertEqual(len(t1["body"]), 8)
        ids_01 = [item["id"] for item in t1["body"]]
        self.assertEqual(ids_01, ["type", "name", "url", "lang", "login", "vip", "nsfw", "notes"])
        # Check required fields
        for item in t1["body"]:
            if item["id"] == "notes":
                self.assertFalse(item.get("validations", {}).get("required", False))
            else:
                self.assertTrue(item.get("validations", {}).get("required", False))

        # 02_report_broken.yml
        path_02 = os.path.join(self.TEMPLATES_DIR, "02_report_broken.yml")
        with open(path_02, "r", encoding="utf-8") as f:
            t2 = yaml.safe_load(f)
        self.assertEqual(len(t2["body"]), 8)
        ids_02 = [item["id"] for item in t2["body"]]
        self.assertEqual(ids_02, [
            "type", "name", "extension_version", "app_name",
            "affected_part", "description", "reproduction", "additional_info"
        ])

        # Verify extension_version starts EMPTY
        ext_ver = next(item for item in t2["body"] if item["id"] == "extension_version")
        self.assertEqual(ext_ver["type"], "input")
        self.assertNotIn("value", ext_ver.get("attributes", {}), "extension_version must NOT have a predefined value!")
        self.assertTrue(ext_ver["validations"]["required"])
        self.assertEqual(ext_ver["attributes"]["placeholder"], "Ex.: 1.6.60")

        # Verify app_name is a free text input starting EMPTY (NO dropdown)
        app_name = next(item for item in t2["body"] if item["id"] == "app_name")
        self.assertEqual(app_name["type"], "input", "app_name must be an input, not a dropdown")
        self.assertNotIn("value", app_name.get("attributes", {}), "app_name must start empty")
        self.assertNotIn("options", app_name.get("attributes", {}))
        self.assertTrue(app_name["validations"]["required"])
        self.assertEqual(app_name["attributes"]["placeholder"], "Ex.: Mihon, Aniyomi, Komikku, Suwayomi...")

        # Verify affected_part is a dropdown (NOT 12 checkboxes)
        aff_part = next(item for item in t2["body"] if item["id"] == "affected_part")
        self.assertEqual(aff_part["type"], "dropdown")
        self.assertEqual(len(aff_part["attributes"]["options"]), 9)
        self.assertIn("Leitor / Imagens", aff_part["attributes"]["options"])
        self.assertTrue(aff_part["validations"]["required"])

        # Verify additional_info is optional
        add_info = next(item for item in t2["body"] if item["id"] == "additional_info")
        self.assertFalse(add_info.get("validations", {}).get("required", False))

        # 03_report_url_change.yml
        path_03 = os.path.join(self.TEMPLATES_DIR, "03_report_url_change.yml")
        with open(path_03, "r", encoding="utf-8") as f:
            t3 = yaml.safe_load(f)
        self.assertEqual(len(t3["body"]), 5)
        ids_03 = [item["id"] for item in t3["body"]]
        self.assertEqual(ids_03, ["type", "name", "old_url", "new_url", "notes"])
        self.assertNotIn("extension_version", ids_03, "03 must not require extension_version")

        # 04_report_dead_source.yml
        path_04 = os.path.join(self.TEMPLATES_DIR, "04_report_dead_source.yml")
        with open(path_04, "r", encoding="utf-8") as f:
            t4 = yaml.safe_load(f)
        self.assertEqual(len(t4["body"]), 4)
        ids_04 = [item["id"] for item in t4["body"]]
        self.assertEqual(ids_04, ["type", "name", "description", "notes"])
        # Check there is no markdown type at the top
        types_04 = [item["type"] for item in t4["body"]]
        self.assertNotIn("markdown", types_04, "04 must not have giant markdown warning banner")

        # 05_request_feature.yml
        path_05 = os.path.join(self.TEMPLATES_DIR, "05_request_feature.yml")
        with open(path_05, "r", encoding="utf-8") as f:
            t5 = yaml.safe_load(f)
        self.assertEqual(len(t5["body"]), 4)
        ids_05 = [item["id"] for item in t5["body"]]
        self.assertEqual(ids_05, ["summary", "description", "related_extension", "extra"])
        self.assertNotIn("purpose", ids_05, "05 must consolidate purpose into description")


if __name__ == "__main__":
    unittest.main()
