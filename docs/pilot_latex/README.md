# Pilot Documents (LaTeX)

This folder contains participant-facing and operator-facing PDF materials for the
eight-person pilot study.

Files:

- `consentimiento_piloto.tex`: informed consent form in Spanish.
- `plantilla_operativa_piloto.tex`: operational checklist and participant tracking sheet.

Compile from this folder with:

```powershell
latexmk -pdf -interaction=nonstopmode -file-line-error consentimiento_piloto.tex
latexmk -pdf -interaction=nonstopmode -file-line-error plantilla_operativa_piloto.tex
```
