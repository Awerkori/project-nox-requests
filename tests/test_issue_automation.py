#!/usr/bin/env python3
"""Project Nox Requests - Automation Logic Unit & Edge Case Test Suite
Simulates the GitHub Actions JavaScript workflow logic for:
1. Title normalization (prevent duplicates, extract clean titles, format prefixes)
2. Type classification (Mangá vs Anime mutual exclusivity)
3. Category classification (Nova extensão, Problema na extensão, etc.)
4. NSFW +18 classification (Sim -> add, Não -> remove)
5. Initial status (Em análise)
6. Idempotence on multiple executions and edits
"""

import re
import unittest

def simulate_workflow(issue_title, issue_body, current_labels, is_closed=False):
    title = issue_title.strip()
    body = issue_body or ""
    labels = set(current_labels)
    labels_to_add = set()
    labels_to_remove = set()

    # Determine category
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
        # Fallback from body inspection
        if "Qual extensão está apresentando o problema?" in body or "Parte afetada" in body:
            category = "Problema na extensão"
        elif "URL oficial do site" in body and "Precisa de login?" in body:
            category = "Nova extensão"
        elif "Domínio ou URL antigo" in body:
            category = "Mudança de domínio"
        elif "O que aconteceu com a fonte?" in body:
            category = "Fonte indisponível"
        elif "Proposta de melhoria" in body or "Título ou resumo da sugestão" in body:
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
        fonte_name = extract_field(r'###\s*Nome da fonte/site\s*\r?\n+([^\r\n#]+)')
        final_name = fonte_name or clean_title or "Nova fonte"
        desired_title = f"[Nova extensão]: {final_name}"

    elif category == "Problema na extensão":
        ext_name = extract_field(r'###\s*(?:Qual extensão está apresentando o problema\?|Nome da extensão)\s*\r?\n+([^\r\n#]+)')
        # If clean_title is already "extName — summary" or starts with "extName -"
        if ext_name:
            # Check if clean_title already starts with ext_name
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
        summary = extract_field(r'###\s*Título ou resumo da sugestão\s*\r?\n+([^\r\n#]+)')
        final_summary = clean_title or summary or "Sugestão"
        desired_title = f"[Sugestão]: {final_summary}"

    # Clean double dashes or spaces
    desired_title = re.sub(r'\s*—\s*—\s*', ' — ', desired_title)

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
    def test_nova_extensao_natural_title(self):
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
        self.assertIn("Nova extensão", res["final_labels"])
        self.assertIn("Em análise", res["final_labels"])
        self.assertNotIn("Conteúdo +18", res["final_labels"])

    def test_nova_extensao_with_nsfw_anime(self):
        body = """### 📌 Informações da extensão
### Tipo de extensão
Anime
### Nome da fonte/site
HentaiStream
### URL oficial do site
https://hentaistream.example
### O site possui conteúdo +18?
Sim
"""
        res = simulate_workflow("HentaiStream", body, ["Nova extensão"])
        self.assertEqual(res["title"], "[Nova extensão]: HentaiStream")
        self.assertIn("Anime", res["final_labels"])
        self.assertIn("Conteúdo +18", res["final_labels"])
        self.assertNotIn("Mangá", res["final_labels"])

    def test_prevent_duplicate_prefixes(self):
        body = """### 📌 Informações da extensão
### Tipo de extensão
Mangá
### Nome da fonte/site
MangaLivre.lat
"""
        res1 = simulate_workflow("[Nova extensão]: MangaLivre.lat", body, ["Nova extensão", "Mangá"])
        self.assertEqual(res1["title"], "[Nova extensão]: MangaLivre.lat")

        res2 = simulate_workflow("[Nova extensão]: [Nova extensão]: MangaLivre.lat", body, ["Nova extensão", "Mangá"])
        self.assertEqual(res2["title"], "[Nova extensão]: MangaLivre.lat")

    def test_bug_report_natural_title_and_app(self):
        body = """### 📌 Identificação da extensão
### Tipo de extensão
Mangá
### Qual extensão está apresentando o problema?
ManHQ
### Qual versão da extensão você está utilizando?
1.6.60
### 📱 Aplicativo utilizado
### Aplicativo utilizado
Mihon
### 🐛 Detalhes do problema
### O que está acontecendo?
Erro ao carregar capítulos
"""
        res = simulate_workflow("Erro ao carregar capítulos da ManHQ", body, ["Problema na extensão"])
        self.assertEqual(res["title"], "[Problema na extensão]: ManHQ — Erro ao carregar capítulos da ManHQ")
        self.assertIn("Mangá", res["final_labels"])
        self.assertIn("Problema na extensão", res["final_labels"])
        self.assertIn("Em análise", res["final_labels"])

    def test_bug_report_with_clean_extension_only_title(self):
        body = """### 📌 Identificação da extensão
### Tipo de extensão
Anime
### Qual extensão está apresentando o problema?
AnimeFire
### Qual versão da extensão você está utilizando?
Não sei
### 📱 Aplicativo utilizado
### Aplicativo utilizado
Aniyomi
"""
        res = simulate_workflow("AnimeFire", body, ["Problema na extensão"])
        self.assertEqual(res["title"], "[Problema na extensão]: AnimeFire")
        self.assertIn("Anime", res["final_labels"])

    def test_edit_type_from_manga_to_anime(self):
        body = """### 📌 Informações da extensão
### Tipo de extensão
Anime
### Nome da fonte/site
AnimeFire
"""
        # User had Mangá label before, but now edited form to Anime
        res = simulate_workflow("AnimeFire", body, ["Nova extensão", "Mangá", "Em análise"])
        self.assertIn("Anime", res["final_labels"])
        self.assertNotIn("Mangá", res["final_labels"])
        self.assertIn("Mangá", res["labels_to_remove"])

    def test_edit_nsfw_from_sim_to_nao(self):
        body = """### 📌 Informações da extensão
### Tipo de extensão
Mangá
### Nome da fonte/site
SukiMangas
### O site possui conteúdo +18?
Não
"""
        # User previously had Conteúdo +18, now corrects to Não
        res = simulate_workflow("SukiMangas", body, ["Nova extensão", "Mangá", "Conteúdo +18"])
        self.assertNotIn("Conteúdo +18", res["final_labels"])
        self.assertIn("Conteúdo +18", res["labels_to_remove"])

    def test_domain_change_normalization(self):
        body = """### 📌 Identificação da extensão
### Tipo de extensão
Mangá
### Nome da extensão
SukiMangas
### Domínio ou URL antigo
https://antigo.com
### Novo domínio ou URL oficial
https://novo.com
"""
        res = simulate_workflow("Novo link do site SukiMangas", body, ["Mudança de domínio"])
        self.assertEqual(res["title"], "[Mudança de domínio]: SukiMangas")
        self.assertIn("Mudança de domínio", res["final_labels"])

    def test_dead_source_normalization(self):
        body = """### 📌 Identificação da fonte
### Tipo de extensão
Mangá
### Nome da extensão
GoldenMangas
"""
        res = simulate_workflow("GoldenMangas caiu", body, ["Fonte indisponível"])
        self.assertEqual(res["title"], "[Fonte indisponível]: GoldenMangas")
        self.assertIn("Fonte indisponível", res["final_labels"])

    def test_feature_request_normalization(self):
        body = """### 💡 Proposta de melhoria
### Título ou resumo da sugestão
Filtro por ano de lançamento
"""
        res = simulate_workflow("Filtro por ano de lançamento", body, ["Sugestão"])
        self.assertEqual(res["title"], "[Sugestão]: Filtro por ano de lançamento")
        self.assertIn("Sugestão", res["final_labels"])


if __name__ == "__main__":
    unittest.main()
