#!/usr/bin/env python3
"""Temas que todo mundo reconhece — jogos, desenhos, filmes, Brasil — para musicas/temas.

    python tools/baixar_temas.py               # mede os candidatos e lista a escolha, sem gravar
    python tools/baixar_temas.py --baixar      # grava a escolha no acervo, com crédito
    python tools/baixar_temas.py --so jogos    # só uma categoria (ou parte do nome da obra)
    python tools/baixar_temas.py --navegador   # abre no navegador o que só se baixa à mão

Por que existe: o dono do projeto pediu música "marcante" (Undertale, a abertura de Gravity
Falls, o Top Gun do NES, o tema do Senna), e o acervo de bandas tem artista que ninguém conhece.
Aqui a lista é escrita à mão, em TEMAS, e para cada tema a ferramenta busca as versões em até
três fontes, mede cada uma e fica com a melhor para dois flybacks:

  vgmusic   https://www.vgmusic.com/   MIDIs de jogo sequenciados à mão, uma página por
            plataforma, com o nome de quem sequenciou. Música de NES e de Game Boy é feita de
            duas ondas quadradas e um triângulo: cabe inteira em dois flybacks. SNES, Mega
            Drive, N64 e PC têm 8 vozes ou mais, e ficam para a montagem de seis.
  pdmx      partituras do MuseScore marcadas como domínio público ou CC0 (o catálogo e os MIDIs
            ficam em ~/pdmx, os mesmos do baixar_pdmx.py).
  lakh      o acervo Lakh, pelo rawl.rocks, o mesmo das bandas: tem alguns temas de filme e TV.

O BitMidi tem muito tema de TV, mas o robots.txt dele proíbe robôs na pasta dos arquivos
(/uploads/), então dele a ferramenta não baixa nada: com --navegador ela abre a página no
navegador, o dono do projeto clica em baixar, e o arquivo que cair em Downloads vai para o acervo
com o crédito. A confirmação continua vindo de uma pessoa.

A medida é a do curar_acervo: quanto da música sobrevive em dois canais monofônicos
(aproveitamento) e em seis (aproveitamento_n). Arquivo de uma parte só perde para um de várias,
porque não há o que pôr no segundo flyback.

Os temas são obras protegidas, em transcrições de fã: valem as regras de crédito do
USO-EDUCACIONAL.md, como as bandas. Os downloads ficam em ~/.cache/flyback-temas, e a varredura
espera PAUSA segundos entre chamadas, com identificação no User-Agent.

Só usa a biblioteca padrão, mais o pandas para ler o catálogo do PDMX.
"""
import argparse
import html
import json
import re
import sys
import tarfile
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'tools'))
from curar_acervo import ler_midi, aproveitamento, aproveitamento_n  # noqa: E402

DESTINO = RAIZ / 'musicas' / 'temas'
CACHE = Path.home() / '.cache' / 'flyback-temas'
PDMX = Path.home() / 'pdmx'
UA = 'flyback-midi/1.0 (https://github.com/joaohauch/flyback-midi) python-urllib'
PAUSA = 1.0
VGM = 'https://www.vgmusic.com/music/'
PLATAFORMA = {
    'nes': 'console/nintendo/nes', 'snes': 'console/nintendo/snes', 'gameboy': 'console/nintendo/gameboy',
    'n64': 'console/nintendo/n64', 'genesis': 'console/sega/genesis', 'ps1': 'console/sony/ps1',
    'windows': 'computer/microsoft/windows', 'arcade': 'other/miscellaneous/arcade',
}
LAKH_INDEX = 'https://rawl.rocks/lakh-index.json'
LAKH_DADOS = 'https://rawl.rocks/lakh-data'
CREDITO_PDMX = 'via PDMX (Long et al., 2024, CC BY 4.0)'
LICENCA = 'obra protegida — uso educacional sem fins lucrativos'


def V(plataforma, jogo, faixa):
    return ('vgmusic', plataforma, jogo, faixa)


def P(titulo):
    return ('pdmx', titulo)


def L(artista, arquivo):
    return ('lakh', artista, arquivo)


def B(slug):
    """Página do BitMidi: só pelo navegador, com o clique do dono do projeto (ver --navegador)."""
    return ('bitmidi', slug)


# Remix, medley, mistura de músicas e arranjo para outro instrumento não são o tema que se
# reconhece: na primeira rodada, a melhor nota de Super Mario era "Overworld (Night Court Remix)"
# e a de Arquivo X, "X-Files lateralus".
RX_FORA = re.compile(r'remix|medley|mash.?up|lateralus|mmadd|composition project|\bcover\b|'
                     r'arrangement|\barr\.|violin part|for (tuba|trombone|clarinet|accordion)', re.I)
DUR_MAX = 6.5 * 60


# (categoria, obra, título, quem compôs, fontes). Expressões sem distinção de maiúsculas.
TEMAS = [
    # --- jogos: NES e Game Boy cabem em dois flybacks; o resto pede mais
    ('jogos', 'Undertale', 'Megalovania', 'Toby Fox', [V('windows', r'^Undertale$', r'^Megalovania'), P(r'megalovania')]),
    ('jogos', 'Undertale', 'Hopes and Dreams', 'Toby Fox', [V('windows', r'^Undertale$', r'^Hopes and Dreams$')]),
    ('jogos', 'Undertale', 'Spider Dance', 'Toby Fox', [V('windows', r'^Undertale$', r'^Spider Dance')]),
    ('jogos', 'Undertale', 'Bonetrousle', 'Toby Fox', [V('windows', r'^Undertale$', r'^Bonetrousle')]),
    ('jogos', 'Undertale', 'Fallen Down', 'Toby Fox', [V('windows', r'^Undertale$', r'^Fallen Down')]),
    ('jogos', 'Top Gun (NES)', 'Abertura', 'Konami', [V('nes', r'^Top Gun$', r'demo|title')]),
    ('jogos', 'Top Gun (NES)', 'Reabastecimento', 'Konami', [V('nes', r'^Top Gun$', r'fuel')]),
    ('jogos', 'Super Mario Bros.', 'Tema principal', 'Koji Kondo', [V('nes', r'^Super Mario Bros\.?$', r'overworld|ground|main'), P(r'^super mario bros\.? theme')]),
    ('jogos', 'Super Mario Bros.', 'Subterrâneo', 'Koji Kondo', [V('nes', r'^Super Mario Bros\.?$', r'underground|underworld')]),
    ('jogos', 'The Legend of Zelda', 'Tema principal', 'Koji Kondo', [V('nes', r'^Legend of Zelda, The$', r'overworld|main|title')]),
    ('jogos', 'Tetris', 'Tipo A (Korobeiniki)', 'tradicional russo, arranjo de Hirokazu Tanaka', [V('gameboy', r'^Tetris$', r'type.?a|a.?type|music.?a|korobeiniki')]),
    ('jogos', 'Pokémon Red e Blue', 'Abertura', 'Junichi Masuda', [V('gameboy', r'^Pok.mon \(Red, Blue, Yellow\)$', r'opening|title|intro')]),
    ('jogos', 'Pokémon Red e Blue', 'Batalha', 'Junichi Masuda', [V('gameboy', r'^Pok.mon \(Red, Blue, Yellow\)$', r'battle')]),
    ('jogos', 'Mega Man 2', 'Dr. Wily, fase 1', 'Takashi Tateishi', [V('nes', r'^Mega Man (2|II)$', r'wily.{0,12}(stage )?1\b|wily.?s castle')]),
    ('jogos', 'Castlevania', 'Vampire Killer', 'Kinuyo Yamashita', [V('nes', r'^Castlevania$', r'vampire killer|stage 1'), P(r'vampire killer')]),
    ('jogos', 'Contra', 'Selva', 'Kazuki Muraoka', [V('nes', r'^Contra$', r'jungle|stage 1|level 1')]),
    ('jogos', 'Sonic the Hedgehog', 'Green Hill Zone', 'Masato Nakamura', [V('genesis', r'^Sonic the Hedgehog$', r'green hill'), P(r'green hill zone')]),
    ('jogos', 'Street Fighter II', 'Tema do Guile', 'Yoko Shimomura', [V('snes', r'Street Fighter II', r'guile'), V('arcade', r'Street Fighter II', r'guile'), P(r"guile'?s theme")]),
    ('jogos', 'Super Mario 64', 'Bob-omb Battlefield', 'Koji Kondo', [V('n64', r'^Super Mario 64$', r'bob.?omb|main theme')]),
    ('jogos', 'Final Fantasy VII', 'Batalha', 'Nobuo Uematsu', [V('ps1', r'^Final Fantasy (7|VII)$', r'fighting|battle')]),
    ('jogos', 'Chrono Trigger', 'Tema principal', 'Yasunori Mitsuda', [V('snes', r'^Chrono Trigger$', r'chrono trigger|main theme|title')]),
    ('jogos', 'Minecraft', 'Sweden', 'C418', [P(r'sweden.*minecraft|minecraft.*sweden')]),
    # --- desenhos e animes
    ('desenhos e animes', 'Gravity Falls', 'Abertura', 'Brad Breeck', [P(r'gravity falls theme')]),
    ('desenhos e animes', 'Pokémon', 'Abertura', 'John Siegler e John Loeffler', [P(r'pok.mon (tv show )?theme|indigo league')]),
    ('desenhos e animes', 'Os Cavaleiros do Zodíaco', 'Pegasus Fantasy', 'Make-Up (Hiroaki Matsuzawa)', [P(r'pegasus fantasy')]),
    ('desenhos e animes', 'Os Simpsons', 'Abertura', 'Danny Elfman', [P(r'^the simpsons')]),
    ('desenhos e animes', 'A Pantera Cor-de-Rosa', 'Tema', 'Henry Mancini', [P(r'pink panther')]),
    # --- filmes e séries
    ('filmes e séries', 'Missão: Impossível', 'Tema', 'Lalo Schifrin', [P(r'mission.? impossible')]),
    ('filmes e séries', 'Piratas do Caribe', "He's a Pirate", 'Klaus Badelt e Hans Zimmer', [P(r"he'?s a pirate|pirates of the caribbean")]),
    ('filmes e séries', 'Jurassic Park', 'Tema', 'John Williams', [P(r'jurassic park')]),
    ('filmes e séries', 'Star Wars', 'Tema principal', 'John Williams', [P(r'star wars (main )?theme|^star wars$')]),
    ('filmes e séries', 'Game of Thrones', 'Abertura', 'Ramin Djawadi', [P(r'game of thrones (main )?theme|^game of thrones$')]),
    ('filmes e séries', 'Rocky', 'Gonna Fly Now', 'Bill Conti', [P(r'gonna fly now|rocky theme')]),
    ('filmes e séries', 'Os Caça-Fantasmas', 'Ghostbusters', 'Ray Parker Jr.', [L(r'^Ray Parker Jr', r'ghostbusters'), P(r'^ghostbusters')]),
    ('filmes e séries', 'Um Tira da Pesada', 'Axel F', 'Harold Faltermeyer', [L(r'^Harold Faltermeyer$', r'axel f'), P(r'axel f')]),
    ('filmes e séries', 'Arquivo X', 'Abertura', 'Mark Snow', [L(r'^Television Theme Songs$', r'x-files'), P(r'x.?files')]),
    ('filmes e séries', 'Miami Vice', 'Tema', 'Jan Hammer', [L(r'^Jan Hammer$', r'miami vice')]),
    ('filmes e séries', '1492: A Conquista do Paraíso', 'Conquest of Paradise', 'Vangelis', [L(r'^Vangelis$', r'1492')]),
    ('filmes e séries', 'O Poderoso Chefão', 'Tema', 'Nino Rota', [L(r'^101 Strings$', r'godfather'), P(r'godfather')]),
    # --- Brasil (o Tema da Vitória só existe no BitMidi: --navegador)
    ('Brasil', 'Fórmula 1', 'Tema da Vitória (Ayrton Senna)', 'Eduardo Souto Neto', [B('senna-mid')]),
    ('Brasil', 'Hino Nacional Brasileiro', 'Hino Nacional', 'Francisco Manuel da Silva e Osório Duque-Estrada', [P(r'^hino nacional brasileiro')]),
    ('Brasil', 'Brasileirinho', 'Brasileirinho', 'Waldir Azevedo', [P(r'^brasileirinho')]),
]


def nfc(s):
    return unicodedata.normalize('NFC', s)


def abrir(url, binario=False):
    """Uma chamada, com cache em disco e PAUSA antes de ir à rede."""
    alvo = CACHE / urllib.parse.quote(url, safe='')[:180]
    if alvo.is_file() and alvo.stat().st_size:
        dados = alvo.read_bytes()
    else:
        time.sleep(PAUSA)
        p = urllib.parse.urlsplit(url)
        url = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path, safe='/%'), p.query, ''))
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=40) as r:
            dados = r.read()
        CACHE.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
    return dados if binario else dados.decode('utf-8', 'replace')


# ------------------------------------------------------------------ fontes
_vgm = {}
RX_LINHA = re.compile(r'<td class="header" colspan="5">(?P<jogo>[^<]*)</td>|'
                      r'<td><a href="(?P<arq>[^"]+\.mid)">(?P<titulo>[^<]*)</a>\s*'
                      r'<td align="right">[^<]*\s*<td align="center">(?P<autor>[^<]*)', re.I)


def vgmusic(plataforma):
    """[(jogo, título, url, quem sequenciou)] de uma página de plataforma do VGMusic."""
    if plataforma not in _vgm:
        base = VGM + PLATAFORMA[plataforma] + '/'
        jogo, itens = '', []
        for m in RX_LINHA.finditer(abrir(base)):
            if m.group('jogo') is not None:
                jogo = html.unescape(m.group('jogo')).strip()
            else:
                itens.append((jogo, html.unescape(m.group('titulo')).strip(), base + m.group('arq'),
                              html.unescape(m.group('autor')).strip()))
        _vgm[plataforma] = itens
    return _vgm[plataforma]


_pdmx = None


def pdmx():
    global _pdmx
    if _pdmx is None:
        import pandas as pd
        d = pd.read_csv(PDMX / 'PDMX.csv', low_memory=False,
                        usecols=['metadata', 'mid', 'title', 'n_favorites', 'n_tracks', 'license',
                                 'license_conflict', 'is_draft', 'song_length.seconds'])
        _pdmx = d[d['mid'].notna() & (d.license_conflict != True) & (d.is_draft != True)  # noqa: E712
                  & (d['song_length.seconds'] > 40)]
    return _pdmx


_lakh = None


def lakh():
    global _lakh
    if _lakh is None:
        _lakh = json.loads(abrir(LAKH_INDEX)).get('artists', [])
    return _lakh


def candidatos(fontes):
    """Cada candidato: dict com fonte, rótulo, como pegar os bytes e o crédito de quem fez."""
    out = []
    for f in fontes:
        if f[0] == 'vgmusic':
            _, plat, rj, rf = f
            for jogo, titulo, url, autor in vgmusic(plat):
                if re.search(rj, jogo, re.I) and re.search(rf, titulo, re.I):
                    out.append(dict(fonte='vgmusic', rotulo=f'{plat} · {jogo} · {titulo}', url=url,
                                    quem=autor or 'autor não identificado', plataforma=plat))
        elif f[0] == 'pdmx':
            d = pdmx()
            m = d[d.title.fillna('').str.contains(f[1], case=False, regex=True)]
            for _, r in m.sort_values('n_favorites', ascending=False).head(6).iterrows():
                out.append(dict(fonte='pdmx', rotulo=f'MuseScore · {r.title}', mid=r['mid'], meta=r['metadata'],
                                licenca_edicao='CC0' if r.license == 'cc-zero' else 'domínio público'))
        elif f[0] == 'bitmidi':
            continue                               # só pelo navegador
        elif f[0] == 'lakh':
            for a in lakh():
                if re.search(f[1], a['name'], re.I):
                    for arq in a['tracks']:
                        if re.search(f[2], arq, re.I):
                            out.append(dict(fonte='lakh', rotulo=f"Lakh · {a['name']} · {arq}",
                                            url=f"{LAKH_DADOS}/{urllib.parse.quote(a['name'])}/{urllib.parse.quote(arq)}",
                                            quem='autor não identificado, publicada em rawl.rocks'))
    return out


def do_tar(arq, caminhos):
    quer = {c.lstrip('./'): c for c in caminhos}
    achou = {}
    if not quer:
        return achou
    with tarfile.open(arq) as t:
        for m in t:
            c = quer.get(m.name.lstrip('./'))
            if c:
                achou[c] = t.extractfile(m).read()
                if len(achou) == len(quer):
                    break
    return achou


def medir(dados):
    faixas = ler_midi(dados)
    fins = [t1 for f in faixas for _, t1, _ in f.notas]
    dur = (max(fins) if fins else 0) + .3
    partes = sum(1 for f in faixas if f.notas)
    return dict(partes=partes, dur=dur, ap2=aproveitamento(faixas, dur), ap6=aproveitamento_n(faixas, dur, 6))


def nota(m):
    """Para dois flybacks: o aproveitamento, com arquivo de uma parte só valendo menos."""
    return m['ap2'] * (.6 if m['partes'] < 2 else 1)


def tema_fontes(obra, titulo):
    return next((t[4] for t in TEMAS if t[1] == obra and t[2] == titulo), [])


def downloads():
    for p in (Path.home() / 'Downloads', Path.home() / 'Transferências'):
        if p.is_dir():
            return p
    return Path.home() / 'Downloads'


def pelo_navegador(temas, espera=180):
    """Abre a página de cada tema no navegador e espera o dono do projeto clicar em baixar.

    O site proíbe robôs na pasta dos arquivos, então quem baixa é a pessoa; daqui só se abre a
    página e se lê a pasta de Downloads. O arquivo novo que aparecer lá (.mid, .midi, .kar) vai
    para o acervo, com o crédito. O original fica em Downloads; salvo direto na pasta de temas,
    ele é movido para o lugar certo."""
    import webbrowser
    pasta = downloads()
    arq_cred = DESTINO / 'creditos.json'
    cred = json.loads(arq_cred.read_text(encoding='utf-8')) if arq_cred.is_file() else {}
    for cat, obra, titulo, compositor, fontes in temas:
        for f in fontes:
            if f[0] != 'bitmidi':
                continue
            rel = nfc(f'{cat}/{nome_arquivo(obra)}/{nome_arquivo(titulo)}.mid')
            if (DESTINO / rel).is_file():
                print(f'   {titulo}: já está no acervo')
                continue
            pagina = f'https://bitmidi.com/{f[1]}'
            # o navegador pode perguntar onde salvar: além de Downloads, olha a pasta de temas
            pastas = [pasta, DESTINO] + [x for x in DESTINO.rglob('*') if x.is_dir()]
            antes = {x for q in pastas if q.is_dir() for x in q.iterdir()}
            inicio = time.time()
            print(f'   {titulo}: abri {pagina} — clique em baixar (espero {espera} s, em {pasta})', flush=True)
            webbrowser.open(pagina)
            novo = None
            while time.time() - inicio < espera and not novo:
                time.sleep(1)
                for x in (y for q in pastas if q.is_dir() for y in q.iterdir()):
                    if x not in antes and x.suffix.lower() in ('.mid', '.midi', '.kar') and x.stat().st_size:
                        novo = x
                        break
            if not novo:
                print('     nada chegou; fica para a próxima')
                continue
            time.sleep(1)                          # o navegador termina de gravar
            dados = novo.read_bytes()
            m = medir(dados)
            alvo = DESTINO / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(dados)
            if novo.resolve().is_relative_to(DESTINO.resolve()) and novo.resolve() != alvo.resolve():
                novo.unlink()                      # salvo direto no acervo: fica só no lugar certo
            cred[rel] = {'autor': compositor, 'artista': obra, 'licenca': LICENCA,
                         'credito': f'composição de {compositor}; transcrição MIDI de autor não identificado, publicada no BitMidi',
                         'transcricao': 'autor não identificado, publicada no BitMidi', 'estilo': cat, 'fonte': pagina,
                         'aproveitamento': round(m['ap2'] * 100), 'aproveitamento6': round(m['ap6'] * 100)}
            arq_cred.write_text(json.dumps(cred, ensure_ascii=False, indent=1), encoding='utf-8')
            print(f'     {novo.name} -> temas/{rel} ({m["partes"]} partes, 2 flybacks {m["ap2"] * 100:.0f}%)')


def nome_arquivo(s):
    return re.sub(r'\s{2,}', ' ', re.sub(r'[\\/:*?"<>|]', '-', s)).strip(' .')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--baixar', action='store_true', help='grava a escolha em musicas/temas, com crédito')
    ap.add_argument('--so', help='só a categoria ou a obra que contenha este texto')
    ap.add_argument('--navegador', action='store_true',
                    help='abre no navegador os temas de site que proíbe robôs; você clica em baixar')
    args = ap.parse_args()

    temas = [t for t in TEMAS if not args.so or args.so.lower() in (t[0] + ' ' + t[1]).lower()]
    if args.navegador:
        pelo_navegador(temas)
        return
    por_tema = []
    for tema in temas:
        try:
            cs = candidatos(tema[4])
        except Exception as e:                     # fonte fora do ar não derruba a lista toda
            print(f'  ! {tema[1]} — {tema[2]}: {e}', file=sys.stderr)
            cs = []
        por_tema.append((tema, cs))

    # os MIDIs do PDMX saem do .tar.gz numa passada só
    tar_mid = do_tar(PDMX / 'mid.tar.gz', [c['mid'] for _, cs in por_tema for c in cs if c['fonte'] == 'pdmx'])
    escolhas = []
    for tema, cs in por_tema:
        medidos = []
        for c in cs:
            if RX_FORA.search(c['rotulo']):
                continue
            try:
                dados = tar_mid.get(c['mid']) if c['fonte'] == 'pdmx' else abrir(c['url'], binario=True)
                if not dados:
                    continue
                m = medir(dados)
                if m['dur'] <= DUR_MAX:
                    medidos.append((nota(m), m, c, dados))
            except Exception as e:
                print(f'  ! {c["rotulo"]}: {e}', file=sys.stderr)
        medidos.sort(key=lambda x: -x[0])
        escolhas.append((tema, medidos))

    cat_ant = None
    for (cat, obra, titulo, compositor, _), medidos in escolhas:
        if cat != cat_ant:
            print(f'\n== {cat}')
            cat_ant = cat
        if not medidos:
            manual = [f for f in tema_fontes(obra, titulo) if f[0] == 'bitmidi']
            print(f'   {obra} — {titulo}: ' + ('pelo navegador (--navegador)' if manual else 'NÃO ACHEI'))
            continue
        _, m, c, _ = medidos[0]
        print(f'   {obra} — {titulo}: {m["partes"]:2d} partes, {m["dur"] / 60:4.1f} min, '
              f'2 flybacks {m["ap2"] * 100:3.0f}%, 6 flybacks {m["ap6"] * 100:3.0f}%  ← {c["rotulo"][:70]}'
              f'  ({len(medidos)} versões)')
    achados = sum(1 for _, ms in escolhas if ms)
    print(f'\n{achados} de {len(escolhas)} temas com versão.')
    if not args.baixar:
        print('Nada foi gravado. Rode com --baixar para valer.')
        return

    metas = do_tar(PDMX / 'metadata.tar.gz', [ms[0][2]['meta'] for _, ms in escolhas if ms and ms[0][2]['fonte'] == 'pdmx'])
    arq_cred = DESTINO / 'creditos.json'
    cred = json.loads(arq_cred.read_text(encoding='utf-8')) if arq_cred.is_file() else {}
    for (cat, obra, titulo, compositor, _), medidos in escolhas:
        if not medidos:
            continue
        _, m, c, dados = medidos[0]
        rel = nfc(f'{cat}/{nome_arquivo(obra)}/{nome_arquivo(titulo)}.mid')
        alvo = DESTINO / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
        if c['fonte'] == 'pdmx':
            meta = json.loads(metas.get(c['meta'], b'{}')).get('data', {}).get('score', {})
            usuario = (meta.get('user') or {}).get('name') or 'autor no MuseScore'
            transcricao = f'partitura de {usuario} no MuseScore (edição {c["licenca_edicao"]}); {CREDITO_PDMX}'
            fonte = meta.get('url') or ''
        else:
            transcricao = f'sequenciada por {c["quem"]}' + (' no VGMusic' if c['fonte'] == 'vgmusic' else '')
            fonte = c['url']
        cred[rel] = {
            'autor': compositor,
            'artista': obra,
            'licenca': LICENCA,
            'credito': f'composição de {compositor}; {transcricao}',
            'transcricao': transcricao,
            'estilo': cat,
            'fonte': fonte,
            'aproveitamento': round(m['ap2'] * 100),
            'aproveitamento6': round(m['ap6'] * 100),
        }
    arq_cred.write_text(json.dumps(cred, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'gravados em {DESTINO}')


if __name__ == '__main__':
    main()
