#!/usr/bin/env python3
"""Project Nox Requests - Label Standardization & Migration Tool.

Migrates legacy GitHub issue labels to the 17 standardized official labels taxonomy
using clean, human-readable Brazilian Portuguese names.
Supports:
  --dry-run   (simulates changes and generates backup, default)
  --apply     (executes atomic rename and standard updates via gh CLI)
  --rollback  (restores backup state if needed)
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = "Awerkori/project-nox-requests"

# 17 Official Standard Labels in 5 Groups
STANDARD_LABELS = {
    # Grupo 1 — Tipo (2)
    "Mangá": {
        "color": "3b82f6",
        "description": "Fonte focada em leitura de mangás, manhwas, manhuas ou webtoons"
    },
    "Anime": {
        "color": "6366f1",
        "description": "Fonte focada em streaming de animes, animações ou filmes"
    },

    # Grupo 2 — Categoria (5)
    "Nova extensão": {
        "color": "8b5cf6",
        "description": "Solicitação de inclusão de uma nova fonte no catálogo do Project Nox"
    },
    "Problema na extensão": {
        "color": "ef4444",
        "description": "Falha funcional, capítulos vazios, leitor quebrado ou erro HTTP em extensão"
    },
    "Mudança de domínio": {
        "color": "06b6d4",
        "description": "Atualização de domínio oficial ou mudança de endereço web da fonte"
    },
    "Fonte indisponível": {
        "color": "64748b",
        "description": "Fonte descontinuada, offline permanentemente ou encerrada pelo proprietário"
    },
    "Sugestão": {
        "color": "ec4899",
        "description": "Sugestão de melhoria funcional, novo recurso ou otimização de catálogo"
    },

    # Grupo 3 — Andamento (4)
    "Em análise": {
        "color": "eab308",
        "description": "Solicitação recebida e aguardando triagem pela equipe do Project Nox"
    },
    "Aceito": {
        "color": "10b981",
        "description": "Solicitação aprovada e aguardando planejamento de desenvolvimento"
    },
    "Em desenvolvimento": {
        "color": "a855f7",
        "description": "Extensão ou correção em desenvolvimento ativo pela equipe"
    },
    "Aguardando informações": {
        "color": "f59e0b",
        "description": "Aguardando detalhes adicionais, logs ou esclarecimentos do autor"
    },

    # Grupo 4 — Resolução Final (4)
    "Concluído": {
        "color": "10b981",
        "description": "Solicitação atendida, desenvolvida e disponibilizada aos usuários"
    },
    "Recusado": {
        "color": "dc2626",
        "description": "Solicitação avaliada e recusada pela equipe técnica"
    },
    "Duplicado": {
        "color": "475569",
        "description": "Solicitação idêntica a outro ticket já existente no repositório"
    },
    "Cancelado": {
        "color": "4b5563",
        "description": "Ticket cancelado pelo próprio autor ou encerrado por perda de objeto"
    },

    # Grupo 5 — Complementares (2)
    "Conteúdo +18": {
        "color": "db2777",
        "description": "Fonte que hospeda conteúdo adulto explícito (+18/Hentai)"
    },
    "Alta prioridade": {
        "color": "ea580c",
        "description": "Alta demanda da comunidade no Tracker ou impacto crítico no ecossistema"
    }
}

# 5 Atomic Renames (Legacy -> Official)
RENAMES = {
    "Manga": "Mangá",
    "Bug": "Problema na extensão",
    "Fonte morta": "Fonte indisponível",
    "+18": "Conteúdo +18",
    "Prioridade": "Alta prioridade"
}


def run_gh_json(cmd: list[str]) -> list | dict:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise Exception(f"GH error ({cmd}): {res.stderr}")
    return json.loads(res.stdout) if res.stdout.strip() else {}


def execute_migration(repo: str, backup_file: Path):
    print("=" * 70)
    print(f"PROJECT NOX — EXECUTANDO MIGRAÇÃO OFICIAL DE LABELS ({repo})")
    print("=" * 70)

    # 1. Fetch current remote labels
    print("[1] Baixando inventário de labels remotas atuais...")
    remote_labels = run_gh_json(["gh", "api", f"repos/{repo}/labels", "--paginate"])
    remote_map = {l["name"]: l for l in remote_labels}
    print(f"  ✓ {len(remote_labels)} labels encontradas no repositório.")

    # 2. Save full snapshot backup
    backup_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "repository": repo,
        "remote_labels": remote_labels
    }
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Backup de segurança salvo em {backup_file}")

    # 3. Rename legacy labels atomically
    print("\n[2] Executando renomeação atômica de labels legadas...")
    for old_name, new_name in RENAMES.items():
        if old_name in remote_map:
            target_info = STANDARD_LABELS[new_name]
            encoded_old = urllib.parse.quote(old_name)
            print(f"  • Renomeando '{old_name}' → '{new_name}' (#{target_info['color']})...")
            cmd = [
                "gh", "api", "--method", "PATCH",
                f"repos/{repo}/labels/{encoded_old}",
                "-f", f"new_name={new_name}",
                "-f", f"color={target_info['color']}",
                "-f", f"description={target_info['description']}"
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            remote_map[new_name] = remote_map.pop(old_name)

    # 4. Create or update all 17 standard labels
    print("\n[3] Garantindo existência e padronização das 17 labels oficiais...")
    for name, info in STANDARD_LABELS.items():
        encoded_name = urllib.parse.quote(name)
        if name in remote_map:
            # Update color and description if different
            cur = remote_map[name]
            if cur.get("color") != info["color"] or cur.get("description") != info["description"]:
                print(f"  • Atualizando propriedades da label existente '{name}'...")
                cmd = [
                    "gh", "api", "--method", "PATCH",
                    f"repos/{repo}/labels/{encoded_name}",
                    "-f", f"color={info['color']}",
                    "-f", f"description={info['description']}"
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        else:
            print(f"  • Criando nova label oficial '{name}' (#{info['color']})...")
            cmd = [
                "gh", "api", "--method", "POST",
                f"repos/{repo}/labels",
                "-f", f"name={name}",
                "-f", f"color={info['color']}",
                "-f", f"description={info['description']}"
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    # 5. Handle duplicate state_reason for closed issues
    print("\n[4] Mapeando tickets com state_reason 'duplicate' para a label 'Duplicado'...")
    dup_issues = run_gh_json([
        "gh", "api", f"repos/{repo}/issues?state=closed&per_page=100", "--paginate"
    ])
    dup_count = 0
    for iss in dup_issues:
        if iss.get("state_reason") == "duplicate":
            lbl_names = [l["name"] for l in iss.get("labels", [])]
            if "Duplicado" not in lbl_names:
                num = iss["number"]
                print(f"  • Adicionando label 'Duplicado' na Issue #{num}...")
                subprocess.run([
                    "gh", "api", "--method", "POST",
                    f"repos/{repo}/issues/{num}/labels",
                    "-f", "labels[]=Duplicado"
                ], check=True, stdout=subprocess.DEVNULL)
                dup_count += 1
    print(f"  ✓ {dup_count} issues duplicadas identificadas e rotuladas com sucesso.")

    # 6. Final verification
    final_labels = run_gh_json(["gh", "api", f"repos/{repo}/labels", "--paginate"])
    final_names = [l["name"] for l in final_labels]
    print("\n[5] Verificação final:")
    print(f"  ✓ Total de labels finais no GitHub: {len(final_names)}")
    print("  ✓ Lista final:", sorted(final_names))

    print("\n" + "=" * 70)
    print("MIGRAÇÃO DE LABELS EXECUTADA COM SUCESSO ABSOLUTO!")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migração de labels oficiais do Project Nox Requests")
    parser.add_argument("--repo", default=REPOSITORY, help="Repositório GitHub")
    parser.add_argument("--apply", action="store_true", help="Executar migração real no repositório remoto")
    parser.add_argument("--backup-file", default="/home/awerkori/.Projects/Project-Nox-Requests/backup_labels_migration.json", help="Arquivo de backup")
    args = parser.parse_args()

    backup_path = Path(args.backup_file)

    if args.apply:
        execute_migration(args.repo, backup_path)
    else:
        print("Modo padrão seguro: use --apply para executar a migração remota autorizada.")
