#!/usr/bin/env python3
"""Gera musicas/index.json, a lista que o site usa para mostrar o acervo.

O GitHub Pages não lista pastas, então o site precisa desse índice. O workflow
de publicação roda este script a cada envio; localmente, tools/servir.py
também roda. Só usa a biblioteca padrão do Python.

Regras:
  - entram arquivos .mid .midi .kar .rmi .gp .gp3 .gp4 .gp5 .gpx .musicxml .mxl
  - subpastas viram grupos no acervo (musicas/exemplos/... aparece em "exemplos")
  - um .json com o mesmo nome da música é a configuração pronta dela
    (roteamento e canais), baixada pelo botão "Baixar configuração" do site
  - um creditos.json numa pasta dá autor, licença e fonte dos arquivos dela,
    com caminhos relativos a essa pasta; o site mostra ao abrir a música.
    Os campos copiados para o índice estão em CAMPOS: além de autor e licença,
    'artista' e 'transcricao' (quem compôs e quem transcreveu, que é o que as
    transcrições de banda precisam declarar) e 'popularidade' (de onde saiu a
    ordem do acervo de bandas)
  - musicas/pastas.txt, se existir, dá a ordem das pastas de primeiro nível
    (uma por linha); as que não estiverem lá vêm depois, em ordem alfabética
  - arquivos e pastas começados por ponto são ignorados
"""
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / 'musicas'
TIPOS = {
    '.mid': 'MIDI', '.midi': 'MIDI', '.kar': 'MIDI', '.rmi': 'MIDI',
    '.gp': 'GP', '.gp3': 'GP', '.gp4': 'GP', '.gp5': 'GP', '.gpx': 'GP',
    '.musicxml': 'XML', '.mxl': 'XML',
}
CAMPOS = ('autor', 'artista', 'instrumentos', 'estilo', 'licenca', 'credito',
          'transcricao', 'popularidade', 'posicao', 'vocal', 'aproveitamento', 'aproveitamento6', 'fonte')


def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c)).casefold()


def ler_creditos():
    mapa = {}
    for arq in PASTA.rglob('creditos.json'):
        base = arq.parent.relative_to(PASTA).as_posix()
        try:
            dados = json.loads(arq.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for rel, info in dados.items():
            if isinstance(info, dict):
                mapa[rel if base == '.' else f'{base}/{rel}'] = info
    return mapa


# Categorias do site (nov/2026, pedido do dono do projeto, no lugar de "antigas" e "temas"):
# clássicas, jogos, filmes e séries, rock, pop e transcritas. São campo, não pasta: uma música pode
# estar em mais de uma (o Tetris é jogo e é folclore russo), e as bandas se dividem em rock e pop
# pelo gênero. O grupo é a hierarquia dentro da categoria (Nintendo › Mario, Queen, Alemanha e
# Áustria › Bach), que o site usa no seletor no lugar do cabeçalho de pasta em cada música.
POP = {'pop', 'soul', 'disco', 'folk', 'country', 'eletrônica', 'choro', 'trilha sonora', 'jazz', 'hip-hop', 'gaúcha'}


def categorizar(item, info):
    partes = item['pasta'].split('/') if item['pasta'] else []
    raiz = partes[0] if partes else ''
    cats, grupo = [], ''
    if raiz == 'transcritas':
        cats, grupo = ['transcritas'], item.get('artista') or item.get('autor') or ''
    elif raiz == 'classicos':
        cats, grupo = ['clássicas'], ' › '.join(partes[1:])
    elif raiz == 'folk russo':
        cats, grupo = ['clássicas'], 'Rússia e Leste Europeu › Folclore russo'
    elif raiz == 'exemplos':
        cats, grupo = ['clássicas', 'rock'], 'Arranjos do projeto'
    elif raiz == 'temas':
        cats, grupo = [partes[1]] if len(partes) > 1 else [], ' › '.join(partes[2:])
    elif raiz == 'bandas':
        estilo = (item.get('estilo') or '').casefold()
        cats = ['clássicas'] if estilo == 'baroque' else ['pop'] if estilo in POP else ['rock']
        grupo = partes[1] if len(partes) > 1 else ''
    # Korobeiniki é o tema do Tetris e é folclore russo: nas duas categorias, cada uma com o seu
    # grupo, venha de onde vier (temas, folk russo ou os arranjos do projeto)
    outros = {}
    if 'korobeiniki' in sem_acento(item['titulo']):
        outros = {'jogos': 'Nintendo › Tetris', 'clássicas': 'Rússia e Leste Europeu › Folclore russo'}
    for c in list(info.get('categorias') or []) + list(outros):
        if c not in cats:
            cats.append(c)
    if cats:
        item['categorias'] = cats
    if grupo:
        item['grupo'] = grupo
    grupos = {c: g for c, g in outros.items() if c in cats and c != cats[0] and g != grupo}
    if grupos:
        item['grupos'] = grupos


def ordem_das_pastas():
    arq = PASTA / 'pastas.txt'
    if not arq.is_file():
        return []
    return [l.strip() for l in arq.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')]


def gerar():
    itens, creditos = [], ler_creditos() if PASTA.is_dir() else {}
    if PASTA.is_dir():
        for arq in PASTA.rglob('*'):
            rel = arq.relative_to(PASTA)
            if not arq.is_file() or arq.suffix.lower() not in TIPOS:
                continue
            if any(p.startswith('.') for p in rel.parts):
                continue
            cfg = arq.with_suffix('.json')
            pasta = rel.parent.as_posix()
            item = {
                'arquivo': rel.as_posix(),
                'titulo': unicodedata.normalize('NFC', arq.stem.replace('_', ' ').strip()) or arq.name,
                'tipo': TIPOS[arq.suffix.lower()],
                'pasta': '' if pasta == '.' else pasta,
                'config': cfg.relative_to(PASTA).as_posix() if cfg.is_file() else None,
            }
            info = creditos.get(rel.as_posix(), {})
            item.update({k: info[k] for k in CAMPOS if info.get(k)})
            # Origem: quem transcreveu. O MuScriptor rodado aqui, na GPU ('muscriptor'), ou o do
            # Mirelo, pela interface ou pela API ('mirelo'); sem o campo, MIDI nativo, escrito por
            # uma pessoa. É uma característica da música, não um lugar: fica como campo, que o
            # site mostra em cada linha, em vez de pasta — a mesma música pode existir nas versões.
            texto = (info.get('transcricao') or '') + (info.get('credito') or '')
            if 'MuScriptor' in texto:
                # o site da Kyutai roda o medium, o mesmo que a GPU daqui: é MuScriptor, não Mirelo
                item['origem'] = 'muscriptor' if 'localmente' in texto or 'kyutai.org' in texto else 'mirelo'
            categorizar(item, info)
            itens.append(item)

    ordem = ordem_das_pastas()
    raiz = lambda i: i['pasta'].split('/')[0] if i['pasta'] else ''
    pos = lambda r: (0, 0, '') if r == '' else (1, ordem.index(r), '') if r in ordem else (1, len(ordem), sem_acento(r))
    itens.sort(key=lambda i: (pos(raiz(i)), sem_acento(i['pasta']), sem_acento(i['titulo'])))

    pastas = []
    for i in itens:
        r = raiz(i)
        if r and (not pastas or pastas[-1]['nome'] != r):
            pastas.append({'nome': r, 'musicas': 0})
        if r:
            pastas[-1]['musicas'] += 1

    PASTA.mkdir(exist_ok=True)
    dados = {'gerado': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'pastas': pastas, 'musicas': itens}
    (PASTA / 'index.json').write_text(json.dumps(dados, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return itens


if __name__ == '__main__':
    itens = gerar()
    print(f'{len(itens)} músicas em musicas/index.json')
    contagem = {}
    for i in itens:
        r = i['pasta'].split('/')[0] if i['pasta'] else '(raiz)'
        contagem[r] = contagem.get(r, 0) + 1
    for r, n in contagem.items():
        print(f'  {n:5}  {r}')
