# Pilot Documents (LaTeX)

This folder contains the participant-facing and operator-facing materials used
for the eight-person pilot study.

## Files

- `consentimiento_piloto.tex`
- `consentimiento_piloto.pdf`
- `plantilla_operativa_piloto.tex`
- `plantilla_operativa_piloto.pdf`

## Consent package structure

The consent document is organised as:

1. one information sheet that the participant keeps
2. one signed copy for the participant
3. one signed copy for the researcher / study archive

Recommended printing:

- two-sided if you want to save paper
- one complete consent pack per participant

## Operator sheet

`plantilla_operativa_piloto.pdf` is the print-ready sheet for:

- pre-session checks
- participant tracking
- calibration status
- completion / exclusion notes
- CSV file notes and incidents

## Compile

Compile from this folder with:

```powershell
latexmk -pdf -interaction=nonstopmode -file-line-error consentimiento_piloto.tex
latexmk -pdf -interaction=nonstopmode -file-line-error plantilla_operativa_piloto.tex
```

If the PDF viewer keeps the file locked, close it before recompiling.
