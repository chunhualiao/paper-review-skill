LATEXMK ?= latexmk
NEATO ?= neato

BUILD_DIR := .build
TEX := paper-review-skill-10min-talk.tex
DECK_PDF := paper-review-skill-10min-talk.pdf
DIAGRAM_DOT := paper-review-skill-system-diagram.dot
DIAGRAM_PDF := paper-review-skill-system-diagram.pdf

.PHONY: all clean

all: $(DECK_PDF)

$(DIAGRAM_PDF): $(DIAGRAM_DOT)
	$(NEATO) -n2 -Tpdf $< -o $@

$(DECK_PDF): $(TEX) $(DIAGRAM_PDF)
	mkdir -p $(BUILD_DIR)
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -outdir=$(BUILD_DIR) $(TEX)
	cp $(BUILD_DIR)/$(DECK_PDF) $@

clean:
	$(LATEXMK) -C -outdir=$(BUILD_DIR) $(TEX)
	rm -rf $(BUILD_DIR) $(DECK_PDF) $(DIAGRAM_PDF)
