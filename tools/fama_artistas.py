#!/usr/bin/env python3
"""Mede a fama de cada artista do acervo: visitas por ano ao artigo dele na Wikipedia em inglês.

    python tools/fama_artistas.py            # mede quem falta e mostra a lista, sem gravar
    python tools/fama_artistas.py --aplicar  # grava musicas/artistas.json

Por que existe: o dono do projeto achou a lista de bandas cheia de artista que nunca ouviu falar
(1910 Fruitgum Company, 911, Alive), e pediu para esconder. Contar músicas não serve — ABBA tinha
uma só, e é dele que ele quer mais —, e a popularidade que o organizar_bandas.py guarda é da
música, não do artista (Michael Jackson e Spice Girls ficavam com zero porque a página daquela
música não foi achada). Aqui se mede o artigo do artista: o gerar_acervo.py copia o número para
o índice, e o filtro "só artistas conhecidos" do site usa CONHECIDO como corte.

O artigo é procurado nesta ordem: "<nome> (band)", "(singer)", "(musician)", "(group)", o nome
puro. Página de desambiguação não conta. O que ficar errado se corrige em MANUAL.

Uma chamada por segundo, com identificação no User-Agent. Só biblioteca padrão.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / 'musicas' / 'artistas.json'
UA = 'flyback-midi/1.0 (https://github.com/joaohauch/flyback-midi) python-urllib'
WP = 'https://en.wikipedia.org/w/api.php'
WPV = 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user'
JANELA = ('2025110100', '2026103100')      # doze meses fechados
PAUSA = 1.0
CONHECIDO = 300_000                        # visitas/ano ao artigo do artista; o site lê daqui
SUFIXOS = (' (band)', ' (singer)', ' (musician)', ' (group)', ' (American band)', ' (British band)', '')
# artigo certo quando a busca erra ou o nome da pasta não é o do artigo; None = não é artista
MANUAL = {
    'AC-DC': 'AC/DC', 'Hall and Oates': 'Hall & Oates', 'Allwood Richard': None, 'Purcell Henry': 'Henry Purcell',
    'Christmas Carols': None, 'TV Themes': None, 'Movie Themes': None, 'Disney Themes': None, 'Nintendo': None,
    'Bedroom Audio': None, 'Jun Ishikawa, Dan Miyakawa': None, 'Presidents Of The USA': 'The Presidents of the United States of America',
    'Archies': 'The Archies', 'Manhattans': 'The Manhattans', 'Beau Brummels': 'The Beau Brummels',
}


def get(url):
    time.sleep(PAUSA)
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def artigo_existe(titulo):
    """Título canônico (seguindo redirecionamento), ou None se não existe ou é desambiguação."""
    q = urllib.parse.urlencode({'action': 'query', 'titles': titulo, 'redirects': 1, 'prop': 'pageprops',
                                'ppprop': 'disambiguation', 'format': 'json'})
    d = get(f'{WP}?{q}')
    for p in d.get('query', {}).get('pages', {}).values():
        if 'missing' in p or 'disambiguation' in (p.get('pageprops') or {}):
            return None
        return p['title']
    return None


def visitas(titulo):
    t = urllib.parse.quote(titulo.replace(' ', '_'), safe='')
    try:
        d = get(f'{WPV}/{t}/monthly/{JANELA[0]}/{JANELA[1]}')
    except urllib.error.HTTPError:
        return 0
    return sum(i['views'] for i in d.get('items', []))


def medir(nome):
    if nome in MANUAL:
        if MANUAL[nome] is None:
            return {'artigo': None, 'visitas': 0}
        cands = [MANUAL[nome]]
    else:
        cands = [nome + s for s in SUFIXOS]
    for c in cands:
        t = artigo_existe(c)
        if t:
            return {'artigo': t, 'visitas': visitas(t)}
    return {'artigo': None, 'visitas': 0}


def artistas_do_acervo():
    """Pastas de artista das bandas e o artista do crédito das transcritas."""
    nomes = set()
    bandas = RAIZ / 'musicas' / 'bandas'
    nomes.update(p.name for p in bandas.iterdir() if p.is_dir())
    cred = RAIZ / 'musicas' / 'transcritas' / 'creditos.json'
    if cred.is_file():
        for v in json.loads(cred.read_text(encoding='utf-8')).values():
            if v.get('artista'):
                nomes.add(v['artista'])
    return sorted(nomes, key=str.lower)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--aplicar', action='store_true', help='grava musicas/artistas.json')
    ap.add_argument('--de-novo', action='store_true', help='mede também quem já está no arquivo')
    args = ap.parse_args()
    feito = json.loads(ARQ.read_text(encoding='utf-8')) if ARQ.is_file() else {}
    for nome in artistas_do_acervo():
        if nome in feito and not args.de_novo:
            continue
        try:
            feito[nome] = medir(nome)
        except Exception as e:                      # rede caiu: fica para a próxima rodada
            print(f'  ! {nome}: {e}', file=sys.stderr)
            continue
        print(f'  {feito[nome]["visitas"]:>10,}  {nome}  ←  {feito[nome]["artigo"]}', flush=True)
    conhecidos = sum(1 for v in feito.values() if v['visitas'] >= CONHECIDO)
    print(f'\n{len(feito)} artistas, {conhecidos} com {CONHECIDO:,} visitas/ano ou mais.')
    if args.aplicar:
        ARQ.write_text(json.dumps(dict(sorted(feito.items(), key=lambda kv: kv[0].lower())),
                                  ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'gravado em {ARQ}')
    else:
        print('Nada foi gravado. Rode com --aplicar para valer.')


if __name__ == '__main__':
    main()
