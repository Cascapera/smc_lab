"""
Storage de arquivos estáticos que não derruba o site quando o manifest falta.

Contexto: ligar o `CompressedManifestStaticFilesStorage` (compressão e
cache-busting) tirou o site do ar. O `collectstatic` do Dockerfile rodava com
settings de desenvolvimento, então a imagem saía sem `staticfiles.json`; o
container subia com settings de produção, o storage carregava zero entradas e
todo `{% static %}` levantava `ValueError` — 500 em todas as páginas.

Agravante: o manifest é lido uma única vez, na inicialização do processo. Rodar
`collectstatic` no container em execução gravava o arquivo em disco, mas os
workers do gunicorn seguiam com o cache vazio. Só um restart resolvia.

O Dockerfile agora gera o manifest com settings de produção e falha o build se
ele não existir. Este storage é a segunda camada: com `manifest_strict = False`,
uma entrada ausente devolve o caminho sem hash em vez de levantar exceção. O
pior caso passa a ser "arquivo estático sem cache-busting", e não "site fora".
"""

from __future__ import annotations

import logging

from whitenoise.storage import CompressedManifestStaticFilesStorage

logger = logging.getLogger(__name__)


class ResilientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Manifest com cache-busting, mas que degrada em vez de estourar."""

    # Com o padrão (True), entrada ausente levanta ValueError e derruba a página.
    # Com False, o Django recalcula o hash a partir do arquivo em disco.
    manifest_strict = False

    def stored_name(self, name):
        nome_limpo = self.clean_name(name)

        if self.hash_key(nome_limpo) in self.hashed_files:
            return super().stored_name(name)

        # Manifest ausente ou incompleto. O Django ainda consegue calcular o
        # hash lendo o arquivo, então normalmente isto funciona.
        logger.warning(
            "[static] '%s' não está no manifest; calculando o hash a partir do "
            "arquivo. Rode collectstatic e reinicie o processo.",
            nome_limpo,
        )
        try:
            return super().stored_name(name)
        except Exception as exc:
            # Nem o arquivo existe. Servir o caminho sem hash faz o navegador
            # receber 404 nesse recurso, mas a página renderiza. É sempre melhor
            # do que 500 no site inteiro.
            logger.error(
                "[static] '%s' não pôde ser resolvido (%s); servindo sem hash.",
                nome_limpo,
                exc,
            )
            return nome_limpo
