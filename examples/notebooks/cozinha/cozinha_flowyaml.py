"""FlowYAML na prática: um fluxograma que escolhe o seu jantar.

Este arquivo é o gêmeo em Python puro do notebook `cozinha_flowyaml.ipynb`,
para quem não tem (ou não quer) um Jupyter à mão. O texto que lá era célula de
markdown está aqui como comentário, e o código é o mesmo, na mesma ordem.

    python cozinha_flowyaml.py

Ele lê `cozinha.yaml`, valida, mostra o modelo e grava `cozinha_flow.html` na
pasta atual. Não acessa a rede em momento nenhum.
"""

# # FlowYAML na prática: um fluxograma que escolhe o seu jantar
#
# Este roteiro é um passeio completo pelo pacote **[`flowyaml`](https://pypi.org/project/flowyaml/)**,
# usando um exemplo que qualquer pessoa entende sem esforço: *o que cozinhar hoje
# com o que já existe na cozinha*.
#
# A ideia do pacote cabe em uma frase:
#
# > Você escreve o fluxo em **YAML**. O `flowyaml` devolve um **HTML pronto**, que
# > abre no navegador **sem servidor, sem Python rodando, sem `npm`, sem internet**.
#
# Nada de arrastar caixinha no mouse. O desenho é consequência do texto, o texto
# entra no `git`, e o `diff` de um fluxograma volta a ser legível.
#
# **O que este roteiro faz, na ordem:**
#
# 1. confere a instalação;
# 2. explica o contrato do YAML com um exemplo mínimo;
# 3. mostra a validação — que aponta código do erro, campo e linha;
# 4. carrega o nosso exemplo de seis níveis;
# 5. mostra como um nível chama o outro (`subprocess` + `ref`);
# 6. gera o HTML e diz onde abri-lo;
# 7. mostra o modo ao vivo, para quando o YAML ainda está sendo editado;
# 8. importa um diagrama **Mermaid** já existente, de brinde.
#
# Tempo estimado de leitura executando tudo: uns 10 minutos.


# ## 0. Instalação
#
# Uma dependência só em tempo de execução (`PyYAML`). O motor de layout do
# navegador vem embutido dentro do pacote, então nada é baixado nem na instalação
# nem na hora de ver o diagrama.


# Instalação, uma vez só:
#
#     pip install flowyaml

import flowyaml as fyml

print("flowyaml", fyml.__version__)
print("temas disponíveis:", fyml.theme_names())
print("tipos de nó:", fyml.NODE_TYPES)


# ## 1. O contrato: YAML entra, grafo sai
#
# Um arquivo FlowYAML é UTF-8 com **um ou mais documentos** separados por `---`.
# Cada documento é **um nível** do fluxo, e tem três chaves:
#
# | chave | o que é |
# | --- | --- |
# | `meta` | identidade do nível. `id` é obrigatório; `name`, `version`, `date` e `description` são opcionais. |
# | `nodes` | a lista de caixas. Cada uma tem `id`, `type` e `label`. |
# | `edges` | a lista de setas. Cada uma tem `from` e `to`, que precisam existir *neste mesmo* documento. |
#
# São **sete tipos de nó**, e cada um tem uma forma própria no desenho:
#
# `startEvent` · `endEvent` · `intermediateEvent` · `gateway` · `subprocess` · `state` · `task`
#
# Nas setas, dois campos mudam o que aparece na tela: `tag` é a etiqueta curta que
# fica **em cima da seta**, e `label` é a frase inteira, que aparece só quando o
# mouse passa por cima. Vale também `kind: association` e `style: dotted` para
# ligações que comentam o fluxo em vez de avançá-lo.
#
# Um exemplo mínimo, inteiro:


exemplo_minimo = '''
meta:
  id: cafe
  name: Café da manhã decidido no susto

nodes:
  - id: acordou
    type: startEvent
    label: Acordou
  - id: tem_pao
    type: gateway
    label: Tem pão?
  - id: torrada
    type: task
    label: Torrada com manteiga
  - id: so_cafe
    type: task
    label: Só o café mesmo
  - id: pronto
    type: endEvent
    label: Dia começou

edges:
  - from: acordou
    to: tem_pao
  - from: tem_pao
    to: torrada
    tag: "Sim"
  - from: tem_pao
    to: so_cafe
    tag: "Não"
  - from: torrada
    to: pronto
  - from: so_cafe
    to: pronto
'''

modelo = fyml.load(exemplo_minimo)
print(modelo.model_ids)

nivel = modelo.default_model
for no in nivel.nodes:
    print(f"  {no.type:<18} {no.id:<10} {no.label}")


# ## 2. A validação fala com você
#
# `validate()` **não levanta exceção**: ela devolve uma tupla de problemas
# estruturados. Cada problema traz um `code` estável, a `message`, o `model_id`,
# o `field` exato e a `line`/`column` do YAML.
#
# Isso é o que permite acoplar o `flowyaml` a um pipeline, a um pre-commit ou a um
# agente sem ficar caçando texto de exceção. Tupla vazia significa "pode renderizar".
#
# Vamos quebrar um YAML de propósito, com três erros clássicos de uma vez:


quebrado = '''
meta:
  id: quebrado

nodes:
  - id: inicio
    type: startEvent
    label: Começo
  - id: passo
    type: tarefa            # 1) tipo que não existe (é "task")
    label: Fazer alguma coisa

edges:
  - from: inicio
    to: fantasma            # 2) destino que não existe
  - from: inicio
    to: passo
    tag: No                 # 3) "No" sem aspas vira booleano em YAML
'''

problemas = fyml.validate(quebrado)
print(f"{len(problemas)} problema(s):\n")
for p in problemas:
    print(f"  [{p.code}]")
    print(f"    campo : {p.field}")
    print(f"    linha : {p.line}")
    print(f"    diz   : {p.message}\n")


# Repare no terceiro: **`Yes`, `No`, `On` e `Off` sem aspas não são texto em YAML,
# são booleanos**. É a pegadinha mais comum do formato, e o `flowyaml` devolve uma
# mensagem que diz exatamente isso em vez de deixar o rótulo sumir do desenho.
#
# Em português `Sim` e `Não` não caem nessa armadilha — mas ponha aspas mesmo
# assim, porque é hábito barato e um dia o diagrama vira bilíngue.
#
# E, importante: quando há qualquer problema, `load()` e `render()` levantam
# `FlowYAMLValidationError` e **não devolvem um grafo pela metade**.


try:
    fyml.load(quebrado)
except fyml.FlowYAMLValidationError as erro:
    print(type(erro).__name__, "->", len(erro.issues), "problemas, nenhum grafo parcial devolvido")


# ## 3. O nosso exemplo: seis níveis
#
# O arquivo `cozinha.yaml`, ao lado deste arquivo, tem **seis documentos**:
#
# - `cozinha` — a decisão de porta de geladeira aberta;
# - `ovos`, `macarrao`, `arroz`, `assadeira`, `sopa` — as refeições para onde ela leva.
#
# A lógica do nível de cima é a que a gente usa de verdade: **primeiro o tempo**
# (menos de 20 minutos, ou uma hora sobrando), **depois os ingredientes**, e só no
# fim a técnica.


from pathlib import Path

FONTE = Path("cozinha.yaml")

assert not fyml.validate(FONTE), "o arquivo precisa estar válido antes de seguir"

diagrama = fyml.load(FONTE)
print(f"{len(diagrama)} modelos em um arquivo só\n")

for m in diagrama:
    print(f"  {m.id:<12} {len(m.nodes):>2} nós  {len(m.edges):>2} arestas   {m.name}")


# ## 4. Um nível chama o outro: `subprocess` + `ref`
#
# Aqui está a parte que costuma vender o pacote sozinha.
#
# Um nó do tipo `subprocess` pode carregar a chave `ref` com o `id` de **outro
# modelo do mesmo arquivo**. No HTML gerado, esse nó vira um **botão**: clicou,
# desceu um nível. E como todos os modelos ficam embutidos no mesmo arquivo,
# a navegação funciona **offline, sem servidor nenhum**.
#
# Um `subprocess` **sem** `ref` continua válido — ele só é desenhado como cartão
# de destino, e não como botão. No nosso fluxo, o "Pão na chapa" é exatamente isso.


nivel_topo = diagrama.get("cozinha")

for no in nivel_topo.nodes:
    if no.type == "subprocess":
        destino = f"abre -> {no.ref}" if no.ref else "cartão de destino (sem ref)"
        print(f"  {no.label:<38} {destino}")


# As etiquetas das setas: `tag` vai na tela, `label` vira dica no hover.
for aresta in nivel_topo.edges:
    if aresta.chip:
        dica = f'   (hover: "{aresta.tooltip}")' if aresta.tooltip else ""
        tipo = " [associação pontilhada]" if aresta.dotted else ""
        print(f'  {aresta.source:<14} -> {aresta.target:<14} "{aresta.chip}"{tipo}{dica}')


# ## 5. Gerar o HTML
#
# Uma chamada. `write_html` renderiza e grava, devolvendo o caminho escrito.
#
# - `output="document"` → página completa, com `<!doctype html>`, para abrir direto do disco.
# - `output="fragment"` → um bloco isolado para pendurar dentro de outra página.
# - `model_id` → qual nível abre primeiro. **Todos** continuam embutidos de qualquer forma.
# - `strings` e `lang` → a moldura em volta do diagrama, que a seção 6 explica.


DESTINO = Path("cozinha_flow.html")

# O runtime escreve algumas palavras por conta própria: os botões, a dica do
# canvas, os rótulos que o leitor de tela anuncia e as mensagens de erro.
# `strings` troca essas palavras; o que não for citado aqui continua no padrão.
PT = {
    "back": "Voltar",
    "backAria": "Subir um nível",
    "levels": "Níveis do fluxo",
    "zoomIn": "Aproximar",
    "zoomOut": "Afastar",
    "fit": "Ajustar",
    "fitAria": "Ajustar o diagrama à tela",
    "open": "Abrir etapa",
    "destination": "Destino",
    "showing": "Mostrando",
    "canvasAria": "Diagrama de fluxo",
    "hint": "Arraste para mover · role para ampliar · Tab e Enter abrem uma etapa",
    "nextSteps": "Explorar os próximos passos",
    "level": "Nível",
    "previousLevels": "Níveis anteriores",
    "returnTo": "Voltar para",
    "noModel": "Este documento não contém nenhum modelo renderizável.",
    "noEngine": "O motor de layout embutido não carregou.",
    "layoutFailed": "O motor de layout não conseguiu desenhar este modelo.",
}

caminho = fyml.write_html(
    FONTE,
    DESTINO,
    model_id="cozinha",
    output="document",
    theme=fyml.DEFAULT_THEME,
    strings=PT,
    lang="pt-BR",
)

print(f"gravado: {caminho}  ({caminho.stat().st_size / 1024:.0f} KB)")


# Prova de que o artefato é realmente autossuficiente:
import re

html = caminho.read_text(encoding="utf-8")
externos = re.findall(r'(?:src|href)="https?://[^"]+"', html)

print("referências externas (http/https):", len(externos))
print("modelos embutidos:", len(re.findall(r'"id":"(?:cozinha|ovos|macarrao|arroz|assadeira|sopa)"', html)))
print("\nOs ~1,6 MB são o motor de layout embutido. É o preço de nunca precisar de rede.")


# ## 6. A moldura em volta do diagrama
#
# O grafo fala a língua de quem escreveu o YAML. A moldura em volta dele — botões,
# dica do canvas, rótulos de acessibilidade — falava só inglês até a versão
# `0.1.2.0`. Agora ela é parâmetro, e são quatro deles.
#
# **`strings`** troca o texto que o runtime escreve sozinho. Ele é *mesclado*
# sobre a tabela padrão, então trocar uma chave é trocar uma chave; e uma chave
# que não existe é **recusada**, em vez de ignorada em silêncio — um erro de
# digitação apareceria como inglês no meio de uma página traduzida.
#
# Isso não é só tradução. `"Abrir etapa"` no lugar de `"Open subprocess"` é
# vocabulário: `subprocess` é palavra de BPMN, e nem todo fluxograma está
# modelando um processo de negócio.
#
# **`lang`** (ou `meta.lang`, dentro do próprio YAML) diz em que língua o
# documento está. É o que decide a voz do leitor de tela e a hifenização do
# navegador. Dois deles juntos importam mais do que parece: o rótulo que o leitor
# de tela anuncia é montado grudando o texto do pacote no rótulo do autor, então
# sem `strings` a frase saía metade em inglês e metade em português.
#
# **`scheme`** escolhe a paleta: `auto` (padrão) segue a configuração de quem
# abre o arquivo, `light` e `dark` fixam. As duas paletas viajam dentro do
# arquivo de qualquer jeito — a opção decide o que a página usa, não o que ela
# contém. Impressão sai numa paleta só, nos dois casos.
#
# **`levels`** escolhe como a página mostra onde o leitor está: `breadcrumb`
# (padrão) é a trilha horizontal na barra de cima; `snapshot` troca por uma faixa
# dos níveis acima, com uma miniatura do diagrama de onde você veio, mais um
# contador de nível. A faixa gasta altura para comprar memória visual, então um
# fluxo mais alto que largo prefere a trilha.
#
# E a gaveta de próximos passos aparece sozinha, sem opção: ela lista as etapas
# do nível atual como botões, que é a mesma navegação do canvas — só que
# alcançável por teclado, por leitor de tela e num celular.


# As duas paletas viajam no mesmo arquivo, sempre.
claro = fyml.render(FONTE, model_id="cozinha", strings=PT, lang="pt-BR")
print("tem bloco para o modo escuro:", "prefers-color-scheme: dark" in claro)
print("declara as duas ao navegador:", 'content="light dark"' in claro)

# A faixa de níveis é a alternativa à trilha, e é opt-in.
faixa = fyml.render(FONTE, model_id="cozinha", strings=PT, lang="pt-BR", levels="snapshot")
print('modo de níveis padrão  :', 'data-fy-levels="breadcrumb"' in claro)
print('modo de níveis em faixa:', 'data-fy-levels="snapshot"' in faixa)

# Uma chave inventada não passa silenciosamente.
print()
try:
    fyml.render(FONTE, strings={"vlotar": "Voltar"})
except fyml.FlowYAMLOptionError as erro:
    print("chave desconhecida recusada:", str(erro).split(";")[0])


# ## 7. Ver o resultado aqui mesmo
#
# Duas maneiras.
#
# A **leve** é apontar para o arquivo — quem lê continua com um arquivo pequeno
# e o HTML é servido pelo próprio Jupyter. É a que usamos abaixo.
#
# Clique nos cartões **"Ovo salva qualquer hora"**, **"Macarrão com o que houver"**,
# **"Arroz de ontem vira prato de hoje"**, **"Joga tudo numa assadeira só"** e
# **"Caldo da gaveta de restos"** para descer um nível. Passe o mouse sobre os nós
# e sobre as setas para ver os detalhes escondidos.


# Num notebook, esta era a hora de embutir a página numa célula. Num script,
# o equivalente é abrir o arquivo no navegador padrão. Descomente para abrir:
#
#     import webbrowser
#     webbrowser.open(caminho.resolve().as_uri())

print("abra", caminho.resolve(), "no navegador.")
print("clique nos cartões de refeição para descer um nível;")
print("passe o mouse sobre nós e setas para ver os detalhes escondidos.")


# A **pesada** é embutir o fragmento direto na saída da célula, com
# `output="fragment"`. Fica lindo, funciona offline e sobrevive a um
# `.ipynb` enviado por e-mail — mas carrega ~1,6 MB **para dentro** da saída
# a cada célula dessas.
#
# Deixei desligado por padrão. Vire a chave para `True` se quiser ver.


# O fragmento existe para ser pendurado dentro de outra página (ou, no
# notebook, dentro da saída de uma célula). Aqui só medimos o tamanho dele.
fragmento = fyml.render(FONTE, model_id="ovos", output="fragment")
print(f"fragmento gerado: {len(fragmento) / 1024:.0f} KB")
print("dica: dois fragmentos podem conviver na mesma página —")
print("cada render ganha um prefixo de DOM aleatório, então eles não colidem.")


# ## 8. Enquanto o YAML ainda está mudando
#
# O HTML gerado é uma **fotografia**: ele mostra o YAML como ele estava na hora em
# que foi escrito. Ótimo para entregar, ruim para quem ainda está mexendo.
#
# Para essa fase existe o `serve`: um servidor da biblioteca padrão que relê o
# arquivo a cada requisição. Você salva o `.yaml` no editor, e a página aberta
# acompanha — sem rebuild, sem `watch`, sem recarregar na mão.
#
# ```python
# fyml.serve("cozinha.yaml", open_browser=True)     # bloqueia; Ctrl+C encerra
# ```
#
# ```bash
# flowyaml serve cozinha.yaml --open
# ```
#
# Não rode isso dentro deste arquivo: o serve bloqueia até você encerrá-lo.
# Rode no terminal, ao lado do editor.
#
# E, de brinde, a linha de comando inteira:
#
# ```bash
# flowyaml validate cozinha.yaml
# flowyaml models   cozinha.yaml
# flowyaml render   cozinha.yaml -o cozinha_flow.html
# flowyaml data     cozinha.yaml -o cozinha.data.json
# flowyaml themes
# ```


# ## 9. De brinde: já tem um diagrama em Mermaid?
#
# Então não precisa reescrever nada. O `flowyaml` lê **Mermaid** e **BPMN 2.0** e
# os converte para o mesmo modelo validado — com duas garantias declaradas pelo
# pacote: a saída é **sempre válida** (passa pelo mesmo validador de um arquivo
# escrito à mão) e **nunca carrega geometria**, porque o layout é calculado no
# navegador.
#
# Ou seja: dá para entrar pelo Mermaid, que muita gente já conhece, e sair com
# FlowYAML editável.


mermaid = '''
flowchart TD
    inicio([Chegou a visita]) --> tem_cafe{Tem café coado?}
    tem_cafe -- Sim --> servir[Servir na hora]
    tem_cafe -- Não --> coar[Coar agora, e conversar enquanto passa]
    coar --> servir
    servir --> fim([Visita bem recebida])
'''

importado = fyml.read_mermaid(mermaid)
print("modelos importados:", importado.model_ids, "\n")

# E a volta: de Mermaid para FlowYAML editável em disco.
print(fyml.to_yaml(importado))


# Um Diagram importado vai direto para o render, sem passar por YAML.
pagina = fyml.render(importado, output="document")
print(f"HTML gerado a partir do Mermaid: {len(pagina) / 1024:.0f} KB")
print("pronto para write_html quando você quiser o arquivo em disco.")


# ## 10. Para replicar na sua máquina
#
# ```bash
# pip install flowyaml
# ```
#
# 1. Escreva um `.yaml` com `meta`, `nodes` e `edges`. Comece com dez nós.
# 2. Rode `flowyaml validate arquivo.yaml` até dar limpo — o erro sempre diz a linha.
# 3. Rode `flowyaml serve arquivo.yaml --open` e edite com a página aberta do lado.
# 4. Quando gostar, `flowyaml render arquivo.yaml -o fluxo.html` e mande o arquivo
#    para quem precisar. Ele abre em qualquer navegador, para sempre, sem nada instalado.
#
# **Por que isso importa mais do que parece.** O fluxograma passa a ser um
# artefato de texto: versionado, revisável em *pull request*, gerado por script,
# comparável entre duas datas. E o que você entrega continua sendo um arquivo que
# a pessoa do outro lado só precisa abrir.
#
# ---
#
# *Pacote: `flowyaml`, de Dornelles Multitech — MIT.
# [PyPI](https://pypi.org/project/flowyaml/) · [GitHub](https://github.com/EngDornelles/flowyaml)*
