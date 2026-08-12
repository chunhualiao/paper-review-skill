LATEXMK ?= latexmk
NEATO ?= neato

BUILD_DIR := .build
TEX := research-paper-review-10min-talk.tex
DECK_PDF := research-paper-review-10min-talk.pdf
DIAGRAM_DOT := research-paper-review-system-diagram.dot
DIAGRAM_PDF := research-paper-review-system-diagram.pdf

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
