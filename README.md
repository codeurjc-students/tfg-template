# Plantilla para la memoria del TFG

En este repositorio se establece un formato de plantilla para memorias de Trabajos de Fin de Grado de la Escuela Técnica Superior de Ingeniería Informática (Universidad Rey Juan Carlos), una versión revisada y extendida de la versión original creada por los profesores de la URJC Manuel Rubio Sánchez y Clara Simón de Blas.

## Trabajar con LaTeX

Esta plantilla utiliza LaTeX, un sistema de composición de textos para crear textos académicos estructurados. 
Se recomienda importar el proyecto en la plataforma [Overleaf](https://www.overleaf.com/) (gratuita), que permite escribir documentos LaTeX online sin realizar ninguna instalación:

- Descargamos esta plantilla como un zip: Code > Download ZIP
- Importamos el proyectto en Overleaf: New Project > Upload Project

Se deberá invitar al tutor (usando el correo de la universidad) para que pueda corregir y sugerir cambios. 

## Diferencias respecto a la plantilla oficial

Respecto a la plantilla oficial, se han añadido nuevas funcionalidades, así como documentación y una nueva propuesta de estructura:

* El documento _tfg.tex_ ahora referencia a distintas páginas de la carpeta _pages/_ para facilitar la navegación.
* Se añade una macro para comentar apropiadamente el PDF final, con el fin de que alumno y profesor puedan dejar retroalimentación de manera sencilla en cualquier sección utilizando `\tutor{Un comentario}` o `\alumno{Otro comentario}`
* Se han actualizado algunos paquetes LaTeX para ampliar las opciones de configuración:
  * `color` -> `xcolor`
