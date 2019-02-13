SIZES=16 32 64 120 128 200 1024 152 144

LOGOS=$(addprefix weblate-,$(addsuffix .png,$(SIZES)))

JPGS=weblate-1024.jpg 

STATIC=../weblate/static/weblate-128.png ../weblate/static/weblate-32.png ../weblate/static/weblate-152.png ../weblate/static/weblate-144.png

BUTTONS=weblate-button.png weblate-button-big.png

all: $(LOGOS) $(JPGS) $(STATIC) $(BUTTONS)

weblate-%.png: weblate.svg
	@./svg2png.sh $< $@ $* $* 16

%.jpg: %.png
	convert $< -quality 75 $@

weblate-button.png: weblate-button.svg
	@./svg2png.sh $< $@ 250 50 64

weblate-button-big.png: weblate-button.svg
	@./svg2png.sh $< $@ 500 100 64

../weblate/static/%: %
	cp $< $@
