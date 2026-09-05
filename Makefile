PYTHON ?= python3
PREFIX ?= /usr
BINDIR = $(PREFIX)/bin
LOCALEDIR = $(PREFIX)/share/locale
XSESSIONDIR = /etc/X11/Xsession.d
AUTOSTARTDIR = /etc/xdg/autostart
PO_FILES = $(wildcard po/*.po)
BUILD_LOCALE = build/locale

.PHONY: all compile-translations test check install clean

all: compile-translations

compile-translations:
	@for po in $(PO_FILES); do \
		lang=$${po##*/}; lang=$${lang%.po}; \
		mkdir -p $(BUILD_LOCALE)/$$lang/LC_MESSAGES; \
		msgfmt -o $(BUILD_LOCALE)/$$lang/LC_MESSAGES/minios-thunar-actions.mo $$po; \
	done

test: compile-translations
	MINIOS_THUNAR_TEST_LOCALE_DIR=$(CURDIR)/$(BUILD_LOCALE) \
		$(PYTHON) -m unittest discover -s tests -v

check: compile-translations
	$(PYTHON) -m py_compile bin/minios-thunar-actions bin/minios-thunar-uca-sync tests/*.py
	@for po in $(PO_FILES); do msgfmt --check --check-format -o /dev/null $$po; done
	$(MAKE) test

install:
	install -Dm755 bin/minios-thunar-actions $(DESTDIR)$(BINDIR)/minios-thunar-actions
	install -Dm755 bin/minios-thunar-uca-sync $(DESTDIR)$(BINDIR)/minios-thunar-uca-sync
	install -Dm644 share/X11/Xsession.d/65minios-thunar-uca-sync \
		$(DESTDIR)$(XSESSIONDIR)/65minios-thunar-uca-sync
	install -Dm644 share/xdg/autostart/minios-thunar-uca-sync.desktop \
		$(DESTDIR)$(AUTOSTARTDIR)/minios-thunar-uca-sync.desktop
	@for po in $(PO_FILES); do \
		lang=$${po##*/}; lang=$${lang%.po}; \
		install -d $(DESTDIR)$(LOCALEDIR)/$$lang/LC_MESSAGES; \
		msgfmt -o $(DESTDIR)$(LOCALEDIR)/$$lang/LC_MESSAGES/minios-thunar-actions.mo $$po; \
	done

clean:
	rm -rf build __pycache__ tests/__pycache__
