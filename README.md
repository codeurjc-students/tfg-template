# Plantilla para la memoria del TFG

En este repositorio se establece un formato de plantilla para memorias de Trabajos de Fin de Grado de con temática web dirigidos por los profesores Micael Gallego, Michel Maes, Óscar Soto e Iván Chicano.

Es una versión revisada y extendida de la versión original creada por los profesores de la Universidad Rey Juan Carlos Manuel Rubio Sánchez y Clara Simón de Blas.

## Trabajar con LaTeX

Esta plantilla utiliza LaTeX, un sistema de composición de textos para crear textos académicos estructurados. 

### Uso de LaTeX online

El alumno **deberá** utilizar la plataforma [Overleaf](https://www.overleaf.com/) (gratuita), que permite escribir documentos LaTeX online sin realizar ninguna instalación. El tutor creará un proyecto nuevo en Overleaf e importará este repositorio como plantilla.

### Uso de LaTeX local

En caso de querer trabajar de manera local, es necesario instalar LaTeX y un editor de texto adecuado.

#### Instalación de LaTeX

Para trabajar con LaTeX es necesario instalar una distribución de LaTeX (se recomienda [TeX Live](https://www.tug.org/texlive/))

* [Instalar en Linux](https://www.tug.org/texlive/quickinstall.html)
* [Instalar en Windows](https://www.tug.org/texlive/windows.html)
* [Instalar en MacOS](https://www.tug.org/mactex/)

#### Instalación del IDE + Plugins

Para editar la memoria, se recomienda utilizar [VSCode](https://code.visualstudio.com/) haciendo uso de las siguientes extensiones: 

* [LaTeX Workshop](https://marketplace.visualstudio.com/items?itemName=James-Yu.latex-workshop)
* [LaTeX language support](https://marketplace.visualstudio.com/items?itemName=torn4dom4n.latex-support)

#### Instalación con Docker (opcional)

Haciendo uso de la extensión _LaTeX Workshop_ también es posible dockerizar todos los paquetes LaTeX para no tener que instalar nada en el sistema operativo local:

1. Teniendo [Docker](https://www.docker.com/) instalado, descargamos una imagen que contenga los paquetes LaTeX:

```
$ docker pull tianon/latex
```

2. Abrir el archivo _settings.json_ de VSCode (Ctrl + Shift + P > Preferences: Open Settings) y añadir las siguientes lineas:

```
{
    "latex-workshop.docker.enabled": true,
    "latex-workshop.latex.outDir": "./out",
    "latex-workshop.synctex.afterBuild.enabled": true,
    "latex-workshop.view.pdf.viewer": "tab",
    "latex-workshop.docker.image.latex": "tianon/latex",
}
```

Los archivos resultantes estarán situados en la carpeta `out/`

## Diferencias respecto a la plantilla oficial

Respecto a la plantilla oficial, se han añadido nuevas funcionalidades, así como documentación y una nueva propuesta de estructura:

* El documento _tfg.tex_ ahora referencia a distintas páginas de la carpeta _pages/_ para facilitar la navegación.
* Se utiliza una estructura concreta para organizar el documento, orientada a trabajos con temática web.
* Se oculta la configuración de la configuración del documento en un archivo aparte (_config.tex_) para facilitar su modificación y abstraer detalles técnicos.
* Se añade una macro para comentar apropiadamente el PDF final, con el fin de que alumno y profesor puedan dejar retroalimentación de manera sencilla en cualquier sección.
* Se han actualizado algunos paquetes LaTeX para ampliar las opciones de configuración:
  * `color` -> `xcolor`
* Se añaden ejemplos avanzados de cómo incluir código fuente con resaltado de sintaxis usando el paquete `listings`.
