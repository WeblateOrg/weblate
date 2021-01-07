(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? module.exports = factory() :
  typeof define === 'function' && define.amd ? define(factory) :
  (global = global || self, global.Tribute = factory());
}(this, (function () { 'use strict';

  function _classCallCheck(instance, Constructor) {
    if (!(instance instanceof Constructor)) {
      throw new TypeError("Cannot call a class as a function");
    }
  }

  function _defineProperties(target, props) {
    for (var i = 0; i < props.length; i++) {
      var descriptor = props[i];
      descriptor.enumerable = descriptor.enumerable || false;
      descriptor.configurable = true;
      if ("value" in descriptor) descriptor.writable = true;
      Object.defineProperty(target, descriptor.key, descriptor);
    }
  }

  function _createClass(Constructor, protoProps, staticProps) {
    if (protoProps) _defineProperties(Constructor.prototype, protoProps);
    if (staticProps) _defineProperties(Constructor, staticProps);
    return Constructor;
  }

  function _slicedToArray(arr, i) {
    return _arrayWithHoles(arr) || _iterableToArrayLimit(arr, i) || _nonIterableRest();
  }

  function _arrayWithHoles(arr) {
    if (Array.isArray(arr)) return arr;
  }

  function _iterableToArrayLimit(arr, i) {
    if (!(Symbol.iterator in Object(arr) || Object.prototype.toString.call(arr) === "[object Arguments]")) {
      return;
    }

    var _arr = [];
    var _n = true;
    var _d = false;
    var _e = undefined;

    try {
      for (var _i = arr[Symbol.iterator](), _s; !(_n = (_s = _i.next()).done); _n = true) {
        _arr.push(_s.value);

        if (i && _arr.length === i) break;
      }
    } catch (err) {
      _d = true;
      _e = err;
    } finally {
      try {
        if (!_n && _i["return"] != null) _i["return"]();
      } finally {
        if (_d) throw _e;
      }
    }

    return _arr;
  }

  function _nonIterableRest() {
    throw new TypeError("Invalid attempt to destructure non-iterable instance");
  }

  if (!Array.prototype.find) {
    Array.prototype.find = function (predicate) {
      if (this === null) {
        throw new TypeError('Array.prototype.find called on null or undefined');
      }

      if (typeof predicate !== 'function') {
        throw new TypeError('predicate must be a function');
      }

      var list = Object(this);
      var length = list.length >>> 0;
      var thisArg = arguments[1];
      var value;

      for (var i = 0; i < length; i++) {
        value = list[i];

        if (predicate.call(thisArg, value, i, list)) {
          return value;
        }
      }

      return undefined;
    };
  }

  if (window && typeof window.CustomEvent !== "function") {
    var CustomEvent$1 = function CustomEvent(event, params) {
      params = params || {
        bubbles: false,
        cancelable: false,
        detail: undefined
      };
      var evt = document.createEvent('CustomEvent');
      evt.initCustomEvent(event, params.bubbles, params.cancelable, params.detail);
      return evt;
    };

    if (typeof window.Event !== 'undefined') {
      CustomEvent$1.prototype = window.Event.prototype;
    }

    window.CustomEvent = CustomEvent$1;
  }

  var TributeEvents = /*#__PURE__*/function () {
    function TributeEvents(tribute) {
      _classCallCheck(this, TributeEvents);

      this.tribute = tribute;
      this.tribute.events = this;
    }

    _createClass(TributeEvents, [{
      key: "bind",
      value: function bind(element) {
        element.boundKeydown = this.keydown.bind(element, this);
        element.boundKeyup = this.keyup.bind(element, this);
        element.boundInput = this.input.bind(element, this);
        element.addEventListener("keydown", element.boundKeydown, false);
        element.addEventListener("keyup", element.boundKeyup, false);
        element.addEventListener("input", element.boundInput, false);
      }
    }, {
      key: "unbind",
      value: function unbind(element) {
        element.removeEventListener("keydown", element.boundKeydown, false);
        element.removeEventListener("keyup", element.boundKeyup, false);
        element.removeEventListener("input", element.boundInput, false);
        delete element.boundKeydown;
        delete element.boundKeyup;
        delete element.boundInput;
      }
    }, {
      key: "keydown",
      value: function keydown(instance, event) {
        if (instance.shouldDeactivate(event)) {
          instance.tribute.isActive = false;
          instance.tribute.hideMenu();
        }

        var element = this;
        instance.commandEvent = false;
        TributeEvents.keys().forEach(function (o) {
          if (o.key === event.keyCode) {
            instance.commandEvent = true;
            instance.callbacks()[o.value.toLowerCase()](event, element);
          }
        });
      }
    }, {
      key: "input",
      value: function input(instance, event) {
        instance.inputEvent = true;
        instance.keyup.call(this, instance, event);
      }
    }, {
      key: "click",
      value: function click(instance, event) {
        var tribute = instance.tribute;

        if (tribute.menu && tribute.menu.contains(event.target)) {
          var li = event.target;
          event.preventDefault();
          event.stopPropagation();

          while (li.nodeName.toLowerCase() !== "li") {
            li = li.parentNode;

            if (!li || li === tribute.menu) {
              throw new Error("cannot find the <li> container for the click");
            }
          }

          tribute.selectItemAtIndex(li.getAttribute("data-index"), event);
          tribute.hideMenu(); // TODO: should fire with externalTrigger and target is outside of menu
        } else if (tribute.current.element && !tribute.current.externalTrigger) {
          tribute.current.externalTrigger = false;
          setTimeout(function () {
            return tribute.hideMenu();
          });
        }
      }
    }, {
      key: "keyup",
      value: function keyup(instance, event) {
        if (instance.inputEvent) {
          instance.inputEvent = false;
        }

        instance.updateSelection(this);
        if (event.keyCode === 27) return;

        if (!instance.tribute.allowSpaces && instance.tribute.hasTrailingSpace) {
          instance.tribute.hasTrailingSpace = false;
          instance.commandEvent = true;
          instance.callbacks()["space"](event, this);
          return;
        }

        if (!instance.tribute.isActive) {
          if (instance.tribute.autocompleteMode) {
            instance.callbacks().triggerChar(event, this, "");
          } else {
            var keyCode = instance.getKeyCode(instance, this, event);
            if (isNaN(keyCode) || !keyCode) return;
            var trigger = instance.tribute.triggers().find(function (trigger) {
              return trigger.charCodeAt(0) === keyCode;
            });

            if (typeof trigger !== "undefined") {
              instance.callbacks().triggerChar(event, this, trigger);
            }
          }
        }

        if (instance.tribute.current.mentionText.length < instance.tribute.current.collection.menuShowMinLength) {
          return;
        }

        if ((instance.tribute.current.trigger || instance.tribute.autocompleteMode) && instance.commandEvent === false || instance.tribute.isActive && event.keyCode === 8) {
          instance.tribute.showMenuFor(this, true);
        }
      }
    }, {
      key: "shouldDeactivate",
      value: function shouldDeactivate(event) {
        if (!this.tribute.isActive) return false;

        if (this.tribute.current.mentionText.length === 0) {
          var eventKeyPressed = false;
          TributeEvents.keys().forEach(function (o) {
            if (event.keyCode === o.key) eventKeyPressed = true;
          });
          return !eventKeyPressed;
        }

        return false;
      }
    }, {
      key: "getKeyCode",
      value: function getKeyCode(instance, el, event) {

        var tribute = instance.tribute;
        var info = tribute.range.getTriggerInfo(false, tribute.hasTrailingSpace, true, tribute.allowSpaces, tribute.autocompleteMode);

        if (info) {
          return info.mentionTriggerChar.charCodeAt(0);
        } else {
          return false;
        }
      }
    }, {
      key: "updateSelection",
      value: function updateSelection(el) {
        this.tribute.current.element = el;
        var info = this.tribute.range.getTriggerInfo(false, this.tribute.hasTrailingSpace, true, this.tribute.allowSpaces, this.tribute.autocompleteMode);

        if (info) {
          this.tribute.current.selectedPath = info.mentionSelectedPath;
          this.tribute.current.mentionText = info.mentionText;
          this.tribute.current.selectedOffset = info.mentionSelectedOffset;
        }
      }
    }, {
      key: "callbacks",
      value: function callbacks() {
        var _this = this;

        return {
          triggerChar: function triggerChar(e, el, trigger) {
            var tribute = _this.tribute;
            tribute.current.trigger = trigger;
            var collectionItem = tribute.collection.find(function (item) {
              return item.trigger === trigger;
            });
            tribute.current.collection = collectionItem;

            if (tribute.current.mentionText.length >= tribute.current.collection.menuShowMinLength && tribute.inputEvent) {
              tribute.showMenuFor(el, true);
            }
          },
          enter: function enter(e, el) {
            // choose selection
            if (_this.tribute.isActive && _this.tribute.current.filteredItems) {
              e.preventDefault();
              e.stopPropagation();
              setTimeout(function () {
                _this.tribute.selectItemAtIndex(_this.tribute.menuSelected, e);

                _this.tribute.hideMenu();
              }, 0);
            }
          },
          escape: function escape(e, el) {
            if (_this.tribute.isActive) {
              e.preventDefault();
              e.stopPropagation();
              _this.tribute.isActive = false;

              _this.tribute.hideMenu();
            }
          },
          tab: function tab(e, el) {
            // choose first match
            _this.callbacks().enter(e, el);
          },
          space: function space(e, el) {
            if (_this.tribute.isActive) {
              if (_this.tribute.spaceSelectsMatch) {
                _this.callbacks().enter(e, el);
              } else if (!_this.tribute.allowSpaces) {
                e.stopPropagation();
                setTimeout(function () {
                  _this.tribute.hideMenu();

                  _this.tribute.isActive = false;
                }, 0);
              }
            }
          },
          up: function up(e, el) {
            // navigate up ul
            if (_this.tribute.isActive && _this.tribute.current.filteredItems) {
              e.preventDefault();
              e.stopPropagation();
              var count = _this.tribute.current.filteredItems.length,
                  selected = _this.tribute.menuSelected;

              if (count > selected && selected > 0) {
                _this.tribute.menuSelected--;

                _this.setActiveLi();
              } else if (selected === 0) {
                _this.tribute.menuSelected = count - 1;

                _this.setActiveLi();

                _this.tribute.menu.scrollTop = _this.tribute.menu.scrollHeight;
              }
            }
          },
          down: function down(e, el) {
            // navigate down ul
            if (_this.tribute.isActive && _this.tribute.current.filteredItems) {
              e.preventDefault();
              e.stopPropagation();
              var count = _this.tribute.current.filteredItems.length - 1,
                  selected = _this.tribute.menuSelected;

              if (count > selected) {
                _this.tribute.menuSelected++;

                _this.setActiveLi();
              } else if (count === selected) {
                _this.tribute.menuSelected = 0;

                _this.setActiveLi();

                _this.tribute.menu.scrollTop = 0;
              }
            }
          },
          "delete": function _delete(e, el) {
            if (_this.tribute.isActive && _this.tribute.current.mentionText.length < 1) {
              _this.tribute.hideMenu();
            } else if (_this.tribute.isActive) {
              _this.tribute.showMenuFor(el);
            }
          }
        };
      }
    }, {
      key: "setActiveLi",
      value: function setActiveLi(index) {
        var lis = this.tribute.menu.querySelectorAll("li"),
            length = lis.length >>> 0;
        if (index) this.tribute.menuSelected = parseInt(index);

        for (var i = 0; i < length; i++) {
          var li = lis[i];

          if (i === this.tribute.menuSelected) {
            li.classList.add(this.tribute.current.collection.selectClass);
            var liClientRect = li.getBoundingClientRect();
            var menuClientRect = this.tribute.menu.getBoundingClientRect();

            if (liClientRect.bottom > menuClientRect.bottom) {
              var scrollDistance = liClientRect.bottom - menuClientRect.bottom;
              this.tribute.menu.scrollTop += scrollDistance;
            } else if (liClientRect.top < menuClientRect.top) {
              var _scrollDistance = menuClientRect.top - liClientRect.top;

              this.tribute.menu.scrollTop -= _scrollDistance;
            }
          } else {
            li.classList.remove(this.tribute.current.collection.selectClass);
          }
        }
      }
    }, {
      key: "getFullHeight",
      value: function getFullHeight(elem, includeMargin) {
        var height = elem.getBoundingClientRect().height;

        if (includeMargin) {
          var style = elem.currentStyle || window.getComputedStyle(elem);
          return height + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
        }

        return height;
      }
    }], [{
      key: "keys",
      value: function keys() {
        return [{
          key: 9,
          value: "TAB"
        }, {
          key: 8,
          value: "DELETE"
        }, {
          key: 13,
          value: "ENTER"
        }, {
          key: 27,
          value: "ESCAPE"
        }, {
          key: 32,
          value: "SPACE"
        }, {
          key: 38,
          value: "UP"
        }, {
          key: 40,
          value: "DOWN"
        }];
      }
    }]);

    return TributeEvents;
  }();

  var TributeMenuEvents = /*#__PURE__*/function () {
    function TributeMenuEvents(tribute) {
      _classCallCheck(this, TributeMenuEvents);

      this.tribute = tribute;
      this.tribute.menuEvents = this;
      this.menu = this.tribute.menu;
    }

    _createClass(TributeMenuEvents, [{
      key: "bind",
      value: function bind(menu) {
        var _this = this;

        this.menuClickEvent = this.tribute.events.click.bind(null, this);
        this.menuContainerScrollEvent = this.debounce(function () {
          if (_this.tribute.isActive) {
            _this.tribute.showMenuFor(_this.tribute.current.element, false);
          }
        }, 300, false);
        this.windowResizeEvent = this.debounce(function () {
          if (_this.tribute.isActive) {
            _this.tribute.range.positionMenuAtCaret(true);
          }
        }, 300, false); // fixes IE11 issues with mousedown

        this.tribute.range.getDocument().addEventListener("MSPointerDown", this.menuClickEvent, false);
        this.tribute.range.getDocument().addEventListener("mousedown", this.menuClickEvent, false);
        window.addEventListener("resize", this.windowResizeEvent);

        if (this.menuContainer) {
          this.menuContainer.addEventListener("scroll", this.menuContainerScrollEvent, false);
        } else {
          window.addEventListener("scroll", this.menuContainerScrollEvent);
        }
      }
    }, {
      key: "unbind",
      value: function unbind(menu) {
        this.tribute.range.getDocument().removeEventListener("mousedown", this.menuClickEvent, false);
        this.tribute.range.getDocument().removeEventListener("MSPointerDown", this.menuClickEvent, false);
        window.removeEventListener("resize", this.windowResizeEvent);

        if (this.menuContainer) {
          this.menuContainer.removeEventListener("scroll", this.menuContainerScrollEvent, false);
        } else {
          window.removeEventListener("scroll", this.menuContainerScrollEvent);
        }
      }
    }, {
      key: "debounce",
      value: function debounce(func, wait, immediate) {
        var _arguments = arguments,
            _this2 = this;

        var timeout;
        return function () {
          var context = _this2,
              args = _arguments;

          var later = function later() {
            timeout = null;
            if (!immediate) func.apply(context, args);
          };

          var callNow = immediate && !timeout;
          clearTimeout(timeout);
          timeout = setTimeout(later, wait);
          if (callNow) func.apply(context, args);
        };
      }
    }]);

    return TributeMenuEvents;
  }();

  var TributeRange = /*#__PURE__*/function () {
    function TributeRange(tribute) {
      _classCallCheck(this, TributeRange);

      this.tribute = tribute;
      this.tribute.range = this;
    }

    _createClass(TributeRange, [{
      key: "getDocument",
      value: function getDocument() {
        var iframe;

        if (this.tribute.current.collection) {
          iframe = this.tribute.current.collection.iframe;
        }

        if (!iframe) {
          return document;
        }

        return iframe.contentWindow.document;
      }
    }, {
      key: "positionMenuAtCaret",
      value: function positionMenuAtCaret(scrollTo) {
        var _this = this;

        var context = this.tribute.current,
            coordinates;
        var info = this.getTriggerInfo(false, this.tribute.hasTrailingSpace, true, this.tribute.allowSpaces, this.tribute.autocompleteMode);

        if (typeof info !== 'undefined') {
          if (!this.tribute.positionMenu) {
            this.tribute.menu.style.cssText = "display: block;";
            return;
          }

          if (!this.isContentEditable(context.element)) {
            coordinates = this.getTextAreaOrInputUnderlinePosition(this.tribute.current.element, info.mentionPosition);
          } else {
            coordinates = this.getContentEditableCaretPosition(info.mentionPosition);
          }

          this.tribute.menu.style.cssText = "top: ".concat(coordinates.top, "px;\n                                     left: ").concat(coordinates.left, "px;\n                                     right: ").concat(coordinates.right, "px;\n                                     bottom: ").concat(coordinates.bottom, "px;\n                                     position: absolute;\n                                     display: block;");

          if (coordinates.left === 'auto') {
            this.tribute.menu.style.left = 'auto';
          }

          if (coordinates.top === 'auto') {
            this.tribute.menu.style.top = 'auto';
          }

          if (scrollTo) this.scrollIntoView();
          window.setTimeout(function () {
            var menuDimensions = {
              width: _this.tribute.menu.offsetWidth,
              height: _this.tribute.menu.offsetHeight
            };

            var menuIsOffScreen = _this.isMenuOffScreen(coordinates, menuDimensions);

            var menuIsOffScreenHorizontally = window.innerWidth > menuDimensions.width && (menuIsOffScreen.left || menuIsOffScreen.right);
            var menuIsOffScreenVertically = window.innerHeight > menuDimensions.height && (menuIsOffScreen.top || menuIsOffScreen.bottom);

            if (menuIsOffScreenHorizontally || menuIsOffScreenVertically) {
              _this.tribute.menu.style.cssText = 'display: none';

              _this.positionMenuAtCaret(scrollTo);
            }
          }, 0);
        } else {
          this.tribute.menu.style.cssText = 'display: none';
        }
      }
    }, {
      key: "selectElement",
      value: function selectElement(targetElement, path, offset) {
        var range;
        var elem = targetElement;

        if (path) {
          for (var i = 0; i < path.length; i++) {
            elem = elem.childNodes[path[i]];

            if (elem === undefined) {
              return;
            }

            while (elem.length < offset) {
              offset -= elem.length;
              elem = elem.nextSibling;
            }

            if (elem.childNodes.length === 0 && !elem.length) {
              elem = elem.previousSibling;
            }
          }
        }

        var sel = this.getWindowSelection();
        range = this.getDocument().createRange();
        range.setStart(elem, offset);
        range.setEnd(elem, offset);
        range.collapse(true);

        try {
          sel.removeAllRanges();
        } catch (error) {}

        sel.addRange(range);
        targetElement.focus();
      }
    }, {
      key: "replaceTriggerText",
      value: function replaceTriggerText(text, requireLeadingSpace, hasTrailingSpace, originalEvent, item) {
        var info = this.getTriggerInfo(true, hasTrailingSpace, requireLeadingSpace, this.tribute.allowSpaces, this.tribute.autocompleteMode);

        if (info !== undefined) {
          var context = this.tribute.current;
          var replaceEvent = new CustomEvent('tribute-replaced', {
            detail: {
              item: item,
              instance: context,
              context: info,
              event: originalEvent
            }
          });

          if (!this.isContentEditable(context.element)) {
            var myField = this.tribute.current.element;
            var textSuffix = typeof this.tribute.replaceTextSuffix == 'string' ? this.tribute.replaceTextSuffix : ' ';
            text += textSuffix;
            var startPos = info.mentionPosition;
            var endPos = info.mentionPosition + info.mentionText.length + textSuffix.length;

            if (!this.tribute.autocompleteMode) {
              endPos += info.mentionTriggerChar.length - 1;
            }

            myField.value = myField.value.substring(0, startPos) + text + myField.value.substring(endPos, myField.value.length);
            myField.selectionStart = startPos + text.length;
            myField.selectionEnd = startPos + text.length;
          } else {
            // add a space to the end of the pasted text
            var _textSuffix = typeof this.tribute.replaceTextSuffix == 'string' ? this.tribute.replaceTextSuffix : '\xA0';

            text += _textSuffix;

            var _endPos = info.mentionPosition + info.mentionText.length;

            if (!this.tribute.autocompleteMode) {
              _endPos += info.mentionTriggerChar.length;
            }

            this.pasteHtml(text, info.mentionPosition, _endPos);
          }

          context.element.dispatchEvent(new CustomEvent('input', {
            bubbles: true
          }));
          context.element.dispatchEvent(replaceEvent);
        }
      }
    }, {
      key: "pasteHtml",
      value: function pasteHtml(html, startPos, endPos) {
        var range, sel;
        sel = this.getWindowSelection();
        range = this.getDocument().createRange();
        range.setStart(sel.anchorNode, startPos);
        range.setEnd(sel.anchorNode, endPos);
        range.deleteContents();
        var el = this.getDocument().createElement('div');
        el.innerHTML = html;
        var frag = this.getDocument().createDocumentFragment(),
            node,
            lastNode;

        while (node = el.firstChild) {
          lastNode = frag.appendChild(node);
        }

        range.insertNode(frag); // Preserve the selection

        if (lastNode) {
          range = range.cloneRange();
          range.setStartAfter(lastNode);
          range.collapse(true);
          sel.removeAllRanges();
          sel.addRange(range);
        }
      }
    }, {
      key: "getWindowSelection",
      value: function getWindowSelection() {
        if (this.tribute.collection.iframe) {
          return this.tribute.collection.iframe.contentWindow.getSelection();
        }

        return window.getSelection();
      }
    }, {
      key: "getNodePositionInParent",
      value: function getNodePositionInParent(element) {
        if (element.parentNode === null) {
          return 0;
        }

        for (var i = 0; i < element.parentNode.childNodes.length; i++) {
          var node = element.parentNode.childNodes[i];

          if (node === element) {
            return i;
          }
        }
      }
    }, {
      key: "getContentEditableSelectedPath",
      value: function getContentEditableSelectedPath(ctx) {
        var sel = this.getWindowSelection();
        var selected = sel.anchorNode;
        var path = [];
        var offset;

        if (selected != null) {
          var i;
          var ce = selected.contentEditable;

          while (selected !== null && ce !== 'true') {
            i = this.getNodePositionInParent(selected);
            path.push(i);
            selected = selected.parentNode;

            if (selected !== null) {
              ce = selected.contentEditable;
            }
          }

          path.reverse(); // getRangeAt may not exist, need alternative

          offset = sel.getRangeAt(0).startOffset;
          return {
            selected: selected,
            path: path,
            offset: offset
          };
        }
      }
    }, {
      key: "getTextPrecedingCurrentSelection",
      value: function getTextPrecedingCurrentSelection() {
        var context = this.tribute.current,
            text = '';

        if (!this.isContentEditable(context.element)) {
          var textComponent = this.tribute.current.element;

          if (textComponent) {
            var startPos = textComponent.selectionStart;

            if (textComponent.value && startPos >= 0) {
              text = textComponent.value.substring(0, startPos);
            }
          }
        } else {
          var selectedElem = this.getWindowSelection().anchorNode;

          if (selectedElem != null) {
            var workingNodeContent = selectedElem.textContent;
            var selectStartOffset = this.getWindowSelection().getRangeAt(0).startOffset;

            if (workingNodeContent && selectStartOffset >= 0) {
              text = workingNodeContent.substring(0, selectStartOffset);
            }
          }
        }

        return text;
      }
    }, {
      key: "getLastWordInText",
      value: function getLastWordInText(text) {
        text = text.replace(/\u00A0/g, ' '); // https://stackoverflow.com/questions/29850407/how-do-i-replace-unicode-character-u00a0-with-a-space-in-javascript

        var wordsArray = text.split(/\s+/);
        var worldsCount = wordsArray.length - 1;
        return wordsArray[worldsCount].trim();
      }
    }, {
      key: "getTriggerInfo",
      value: function getTriggerInfo(menuAlreadyActive, hasTrailingSpace, requireLeadingSpace, allowSpaces, isAutocomplete) {
        var _this2 = this;

        var ctx = this.tribute.current;
        var selected, path, offset;

        if (!this.isContentEditable(ctx.element)) {
          selected = this.tribute.current.element;
        } else {
          var selectionInfo = this.getContentEditableSelectedPath(ctx);

          if (selectionInfo) {
            selected = selectionInfo.selected;
            path = selectionInfo.path;
            offset = selectionInfo.offset;
          }
        }

        var effectiveRange = this.getTextPrecedingCurrentSelection();
        var lastWordOfEffectiveRange = this.getLastWordInText(effectiveRange);

        if (isAutocomplete) {
          return {
            mentionPosition: effectiveRange.length - lastWordOfEffectiveRange.length,
            mentionText: lastWordOfEffectiveRange,
            mentionSelectedElement: selected,
            mentionSelectedPath: path,
            mentionSelectedOffset: offset
          };
        }

        if (effectiveRange !== undefined && effectiveRange !== null) {
          var mostRecentTriggerCharPos = -1;
          var triggerChar;
          this.tribute.collection.forEach(function (config) {
            var c = config.trigger;
            var idx = config.requireLeadingSpace ? _this2.lastIndexWithLeadingSpace(effectiveRange, c) : effectiveRange.lastIndexOf(c);

            if (idx > mostRecentTriggerCharPos) {
              mostRecentTriggerCharPos = idx;
              triggerChar = c;
              requireLeadingSpace = config.requireLeadingSpace;
            }
          });

          if (mostRecentTriggerCharPos >= 0 && (mostRecentTriggerCharPos === 0 || !requireLeadingSpace || /[\xA0\s]/g.test(effectiveRange.substring(mostRecentTriggerCharPos - 1, mostRecentTriggerCharPos)))) {
            var currentTriggerSnippet = effectiveRange.substring(mostRecentTriggerCharPos + triggerChar.length, effectiveRange.length);
            triggerChar = effectiveRange.substring(mostRecentTriggerCharPos, mostRecentTriggerCharPos + triggerChar.length);
            var firstSnippetChar = currentTriggerSnippet.substring(0, 1);
            var leadingSpace = currentTriggerSnippet.length > 0 && (firstSnippetChar === ' ' || firstSnippetChar === '\xA0');

            if (hasTrailingSpace) {
              currentTriggerSnippet = currentTriggerSnippet.trim();
            }

            var regex = allowSpaces ? /[^\S ]/g : /[\xA0\s]/g;
            this.tribute.hasTrailingSpace = regex.test(currentTriggerSnippet);

            if (!leadingSpace && (menuAlreadyActive || !regex.test(currentTriggerSnippet))) {
              return {
                mentionPosition: mostRecentTriggerCharPos,
                mentionText: currentTriggerSnippet,
                mentionSelectedElement: selected,
                mentionSelectedPath: path,
                mentionSelectedOffset: offset,
                mentionTriggerChar: triggerChar
              };
            }
          }
        }
      }
    }, {
      key: "lastIndexWithLeadingSpace",
      value: function lastIndexWithLeadingSpace(str, trigger) {
        var reversedStr = str.split('').reverse().join('');
        var index = -1;

        for (var cidx = 0, len = str.length; cidx < len; cidx++) {
          var firstChar = cidx === str.length - 1;
          var leadingSpace = /\s/.test(reversedStr[cidx + 1]);
          var match = true;

          for (var triggerIdx = trigger.length - 1; triggerIdx >= 0; triggerIdx--) {
            if (trigger[triggerIdx] !== reversedStr[cidx - triggerIdx]) {
              match = false;
              break;
            }
          }

          if (match && (firstChar || leadingSpace)) {
            index = str.length - 1 - cidx;
            break;
          }
        }

        return index;
      }
    }, {
      key: "isContentEditable",
      value: function isContentEditable(element) {
        return element.nodeName !== 'INPUT' && element.nodeName !== 'TEXTAREA';
      }
    }, {
      key: "isMenuOffScreen",
      value: function isMenuOffScreen(coordinates, menuDimensions) {
        var windowWidth = window.innerWidth;
        var windowHeight = window.innerHeight;
        var doc = document.documentElement;
        var windowLeft = (window.pageXOffset || doc.scrollLeft) - (doc.clientLeft || 0);
        var windowTop = (window.pageYOffset || doc.scrollTop) - (doc.clientTop || 0);
        var menuTop = typeof coordinates.top === 'number' ? coordinates.top : windowTop + windowHeight - coordinates.bottom - menuDimensions.height;
        var menuRight = typeof coordinates.right === 'number' ? coordinates.right : coordinates.left + menuDimensions.width;
        var menuBottom = typeof coordinates.bottom === 'number' ? coordinates.bottom : coordinates.top + menuDimensions.height;
        var menuLeft = typeof coordinates.left === 'number' ? coordinates.left : windowLeft + windowWidth - coordinates.right - menuDimensions.width;
        return {
          top: menuTop < Math.floor(windowTop),
          right: menuRight > Math.ceil(windowLeft + windowWidth),
          bottom: menuBottom > Math.ceil(windowTop + windowHeight),
          left: menuLeft < Math.floor(windowLeft)
        };
      }
    }, {
      key: "getMenuDimensions",
      value: function getMenuDimensions() {
        // Width of the menu depends of its contents and position
        // We must check what its width would be without any obstruction
        // This way, we can achieve good positioning for flipping the menu
        var dimensions = {
          width: null,
          height: null
        };
        this.tribute.menu.style.cssText = "top: 0px;\n                                 left: 0px;\n                                 position: fixed;\n                                 display: block;\n                                 visibility; hidden;";
        dimensions.width = this.tribute.menu.offsetWidth;
        dimensions.height = this.tribute.menu.offsetHeight;
        this.tribute.menu.style.cssText = "display: none;";
        return dimensions;
      }
    }, {
      key: "getTextAreaOrInputUnderlinePosition",
      value: function getTextAreaOrInputUnderlinePosition(element, position, flipped) {
        var properties = ['direction', 'boxSizing', 'width', 'height', 'overflowX', 'overflowY', 'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize', 'fontSizeAdjust', 'lineHeight', 'fontFamily', 'textAlign', 'textTransform', 'textIndent', 'textDecoration', 'letterSpacing', 'wordSpacing'];
        var isFirefox = window.mozInnerScreenX !== null;
        var div = this.getDocument().createElement('div');
        div.id = 'input-textarea-caret-position-mirror-div';
        this.getDocument().body.appendChild(div);
        var style = div.style;
        var computed = window.getComputedStyle ? getComputedStyle(element) : element.currentStyle;
        style.whiteSpace = 'pre-wrap';

        if (element.nodeName !== 'INPUT') {
          style.wordWrap = 'break-word';
        } // position off-screen


        style.position = 'absolute';
        style.visibility = 'hidden'; // transfer the element's properties to the div

        properties.forEach(function (prop) {
          style[prop] = computed[prop];
        });

        if (isFirefox) {
          style.width = "".concat(parseInt(computed.width) - 2, "px");
          if (element.scrollHeight > parseInt(computed.height)) style.overflowY = 'scroll';
        } else {
          style.overflow = 'hidden';
        }

        div.textContent = element.value.substring(0, position);

        if (element.nodeName === 'INPUT') {
          div.textContent = div.textContent.replace(/\s/g, ' ');
        }

        var span = this.getDocument().createElement('span');
        span.textContent = element.value.substring(position) || '.';
        div.appendChild(span);
        var rect = element.getBoundingClientRect();
        var doc = document.documentElement;
        var windowLeft = (window.pageXOffset || doc.scrollLeft) - (doc.clientLeft || 0);
        var windowTop = (window.pageYOffset || doc.scrollTop) - (doc.clientTop || 0);
        var top = 0;
        var left = 0;

        if (this.menuContainerIsBody) {
          top = rect.top;
          left = rect.left;
        }

        var coordinates = {
          top: top + windowTop + span.offsetTop + parseInt(computed.borderTopWidth) + parseInt(computed.fontSize) - element.scrollTop,
          left: left + windowLeft + span.offsetLeft + parseInt(computed.borderLeftWidth)
        };
        var windowWidth = window.innerWidth;
        var windowHeight = window.innerHeight;
        var menuDimensions = this.getMenuDimensions();
        var menuIsOffScreen = this.isMenuOffScreen(coordinates, menuDimensions);

        if (menuIsOffScreen.right) {
          coordinates.right = windowWidth - coordinates.left;
          coordinates.left = 'auto';
        }

        var parentHeight = this.tribute.menuContainer ? this.tribute.menuContainer.offsetHeight : this.getDocument().body.offsetHeight;

        if (menuIsOffScreen.bottom) {
          var parentRect = this.tribute.menuContainer ? this.tribute.menuContainer.getBoundingClientRect() : this.getDocument().body.getBoundingClientRect();
          var scrollStillAvailable = parentHeight - (windowHeight - parentRect.top);
          coordinates.bottom = scrollStillAvailable + (windowHeight - rect.top - span.offsetTop);
          coordinates.top = 'auto';
        }

        menuIsOffScreen = this.isMenuOffScreen(coordinates, menuDimensions);

        if (menuIsOffScreen.left) {
          coordinates.left = windowWidth > menuDimensions.width ? windowLeft + windowWidth - menuDimensions.width : windowLeft;
          delete coordinates.right;
        }

        if (menuIsOffScreen.top) {
          coordinates.top = windowHeight > menuDimensions.height ? windowTop + windowHeight - menuDimensions.height : windowTop;
          delete coordinates.bottom;
        }

        this.getDocument().body.removeChild(div);
        return coordinates;
      }
    }, {
      key: "getContentEditableCaretPosition",
      value: function getContentEditableCaretPosition(selectedNodePosition) {
        var range;
        var sel = this.getWindowSelection();
        range = this.getDocument().createRange();
        range.setStart(sel.anchorNode, selectedNodePosition);
        range.setEnd(sel.anchorNode, selectedNodePosition);
        range.collapse(false);
        var rect = range.getBoundingClientRect();
        var doc = document.documentElement;
        var windowLeft = (window.pageXOffset || doc.scrollLeft) - (doc.clientLeft || 0);
        var windowTop = (window.pageYOffset || doc.scrollTop) - (doc.clientTop || 0);
        var left = rect.left;
        var top = rect.top;
        var coordinates = {
          left: left + windowLeft,
          top: top + rect.height + windowTop
        };
        var windowWidth = window.innerWidth;
        var windowHeight = window.innerHeight;
        var menuDimensions = this.getMenuDimensions();
        var menuIsOffScreen = this.isMenuOffScreen(coordinates, menuDimensions);

        if (menuIsOffScreen.right) {
          coordinates.left = 'auto';
          coordinates.right = windowWidth - rect.left - windowLeft;
        }

        var parentHeight = this.tribute.menuContainer ? this.tribute.menuContainer.offsetHeight : this.getDocument().body.offsetHeight;

        if (menuIsOffScreen.bottom) {
          var parentRect = this.tribute.menuContainer ? this.tribute.menuContainer.getBoundingClientRect() : this.getDocument().body.getBoundingClientRect();
          var scrollStillAvailable = parentHeight - (windowHeight - parentRect.top);
          coordinates.top = 'auto';
          coordinates.bottom = scrollStillAvailable + (windowHeight - rect.top);
        }

        menuIsOffScreen = this.isMenuOffScreen(coordinates, menuDimensions);

        if (menuIsOffScreen.left) {
          coordinates.left = windowWidth > menuDimensions.width ? windowLeft + windowWidth - menuDimensions.width : windowLeft;
          delete coordinates.right;
        }

        if (menuIsOffScreen.top) {
          coordinates.top = windowHeight > menuDimensions.height ? windowTop + windowHeight - menuDimensions.height : windowTop;
          delete coordinates.bottom;
        }

        if (!this.menuContainerIsBody) {
          coordinates.left = coordinates.left ? coordinates.left - this.tribute.menuContainer.offsetLeft : coordinates.left;
          coordinates.top = coordinates.top ? coordinates.top - this.tribute.menuContainer.offsetTop : coordinates.top;
        }

        return coordinates;
      }
    }, {
      key: "scrollIntoView",
      value: function scrollIntoView(elem) {
        var reasonableBuffer = 20,
            clientRect;
        var maxScrollDisplacement = 100;
        var e = this.menu;
        if (typeof e === 'undefined') return;

        while (clientRect === undefined || clientRect.height === 0) {
          clientRect = e.getBoundingClientRect();

          if (clientRect.height === 0) {
            e = e.childNodes[0];

            if (e === undefined || !e.getBoundingClientRect) {
              return;
            }
          }
        }

        var elemTop = clientRect.top;
        var elemBottom = elemTop + clientRect.height;

        if (elemTop < 0) {
          window.scrollTo(0, window.pageYOffset + clientRect.top - reasonableBuffer);
        } else if (elemBottom > window.innerHeight) {
          var maxY = window.pageYOffset + clientRect.top - reasonableBuffer;

          if (maxY - window.pageYOffset > maxScrollDisplacement) {
            maxY = window.pageYOffset + maxScrollDisplacement;
          }

          var targetY = window.pageYOffset - (window.innerHeight - elemBottom);

          if (targetY > maxY) {
            targetY = maxY;
          }

          window.scrollTo(0, targetY);
        }
      }
    }, {
      key: "menuContainerIsBody",
      get: function get() {
        return this.tribute.menuContainer === document.body || !this.tribute.menuContainer;
      }
    }]);

    return TributeRange;
  }();

  // Thanks to https://github.com/mattyork/fuzzy
  var TributeSearch = /*#__PURE__*/function () {
    function TributeSearch(tribute) {
      _classCallCheck(this, TributeSearch);

      this.tribute = tribute;
      this.tribute.search = this;
    }

    _createClass(TributeSearch, [{
      key: "simpleFilter",
      value: function simpleFilter(pattern, array) {
        var _this = this;

        return array.filter(function (string) {
          return _this.test(pattern, string);
        });
      }
    }, {
      key: "test",
      value: function test(pattern, string) {
        return this.match(pattern, string) !== null;
      }
    }, {
      key: "match",
      value: function match(pattern, string, opts) {
        opts = opts || {};
        var len = string.length,
            pre = opts.pre || '',
            post = opts.post || '',
            compareString = opts.caseSensitive && string || string.toLowerCase();

        if (opts.skip) {
          return {
            rendered: string,
            score: 0
          };
        }

        pattern = opts.caseSensitive && pattern || pattern.toLowerCase();
        var patternCache = this.traverse(compareString, pattern, 0, 0, []);

        if (!patternCache) {
          return null;
        }

        return {
          rendered: this.render(string, patternCache.cache, pre, post),
          score: patternCache.score
        };
      }
    }, {
      key: "traverse",
      value: function traverse(string, pattern, stringIndex, patternIndex, patternCache) {
        // if the pattern search at end
        if (pattern.length === patternIndex) {
          // calculate score and copy the cache containing the indices where it's found
          return {
            score: this.calculateScore(patternCache),
            cache: patternCache.slice()
          };
        } // if string at end or remaining pattern > remaining string


        if (string.length === stringIndex || pattern.length - patternIndex > string.length - stringIndex) {
          return undefined;
        }

        var c = pattern[patternIndex];
        var index = string.indexOf(c, stringIndex);
        var best, temp;

        while (index > -1) {
          patternCache.push(index);
          temp = this.traverse(string, pattern, index + 1, patternIndex + 1, patternCache);
          patternCache.pop(); // if downstream traversal failed, return best answer so far

          if (!temp) {
            return best;
          }

          if (!best || best.score < temp.score) {
            best = temp;
          }

          index = string.indexOf(c, index + 1);
        }

        return best;
      }
    }, {
      key: "calculateScore",
      value: function calculateScore(patternCache) {
        var score = 0;
        var temp = 1;
        patternCache.forEach(function (index, i) {
          if (i > 0) {
            if (patternCache[i - 1] + 1 === index) {
              temp += temp + 1;
            } else {
              temp = 1;
            }
          }

          score += temp;
        });
        return score;
      }
    }, {
      key: "render",
      value: function render(string, indices, pre, post) {
        var rendered = string.substring(0, indices[0]);
        indices.forEach(function (index, i) {
          rendered += pre + string[index] + post + string.substring(index + 1, indices[i + 1] ? indices[i + 1] : string.length);
        });
        return rendered;
      }
    }, {
      key: "filter",
      value: function filter(pattern, arr, opts) {
        var _this2 = this;

        opts = opts || {};
        return arr.reduce(function (prev, element, idx, arr) {
          var str = element;

          if (opts.extract) {
            str = opts.extract(element);

            if (!str) {
              // take care of undefineds / nulls / etc.
              str = '';
            }
          }

          var rendered = _this2.match(pattern, str, opts);

          if (rendered != null) {
            prev[prev.length] = {
              string: rendered.rendered,
              score: rendered.score,
              index: idx,
              original: element
            };
          }

          return prev;
        }, []).sort(function (a, b) {
          var compare = b.score - a.score;
          if (compare) return compare;
          return a.index - b.index;
        });
      }
    }]);

    return TributeSearch;
  }();

  var Tribute = /*#__PURE__*/function () {
    function Tribute(_ref) {
      var _this = this;

      var _ref$values = _ref.values,
          values = _ref$values === void 0 ? null : _ref$values,
          _ref$iframe = _ref.iframe,
          iframe = _ref$iframe === void 0 ? null : _ref$iframe,
          _ref$selectClass = _ref.selectClass,
          selectClass = _ref$selectClass === void 0 ? "highlight" : _ref$selectClass,
          _ref$containerClass = _ref.containerClass,
          containerClass = _ref$containerClass === void 0 ? "tribute-container" : _ref$containerClass,
          _ref$itemClass = _ref.itemClass,
          itemClass = _ref$itemClass === void 0 ? "" : _ref$itemClass,
          _ref$trigger = _ref.trigger,
          trigger = _ref$trigger === void 0 ? "@" : _ref$trigger,
          _ref$autocompleteMode = _ref.autocompleteMode,
          autocompleteMode = _ref$autocompleteMode === void 0 ? false : _ref$autocompleteMode,
          _ref$selectTemplate = _ref.selectTemplate,
          selectTemplate = _ref$selectTemplate === void 0 ? null : _ref$selectTemplate,
          _ref$menuItemTemplate = _ref.menuItemTemplate,
          menuItemTemplate = _ref$menuItemTemplate === void 0 ? null : _ref$menuItemTemplate,
          _ref$lookup = _ref.lookup,
          lookup = _ref$lookup === void 0 ? "key" : _ref$lookup,
          _ref$fillAttr = _ref.fillAttr,
          fillAttr = _ref$fillAttr === void 0 ? "value" : _ref$fillAttr,
          _ref$collection = _ref.collection,
          collection = _ref$collection === void 0 ? null : _ref$collection,
          _ref$menuContainer = _ref.menuContainer,
          menuContainer = _ref$menuContainer === void 0 ? null : _ref$menuContainer,
          _ref$noMatchTemplate = _ref.noMatchTemplate,
          noMatchTemplate = _ref$noMatchTemplate === void 0 ? null : _ref$noMatchTemplate,
          _ref$requireLeadingSp = _ref.requireLeadingSpace,
          requireLeadingSpace = _ref$requireLeadingSp === void 0 ? true : _ref$requireLeadingSp,
          _ref$allowSpaces = _ref.allowSpaces,
          allowSpaces = _ref$allowSpaces === void 0 ? false : _ref$allowSpaces,
          _ref$replaceTextSuffi = _ref.replaceTextSuffix,
          replaceTextSuffix = _ref$replaceTextSuffi === void 0 ? null : _ref$replaceTextSuffi,
          _ref$positionMenu = _ref.positionMenu,
          positionMenu = _ref$positionMenu === void 0 ? true : _ref$positionMenu,
          _ref$spaceSelectsMatc = _ref.spaceSelectsMatch,
          spaceSelectsMatch = _ref$spaceSelectsMatc === void 0 ? false : _ref$spaceSelectsMatc,
          _ref$searchOpts = _ref.searchOpts,
          searchOpts = _ref$searchOpts === void 0 ? {} : _ref$searchOpts,
          _ref$menuItemLimit = _ref.menuItemLimit,
          menuItemLimit = _ref$menuItemLimit === void 0 ? null : _ref$menuItemLimit,
          _ref$menuShowMinLengt = _ref.menuShowMinLength,
          menuShowMinLength = _ref$menuShowMinLengt === void 0 ? 0 : _ref$menuShowMinLengt;

      _classCallCheck(this, Tribute);

      this.autocompleteMode = autocompleteMode;
      this.menuSelected = 0;
      this.current = {};
      this.inputEvent = false;
      this.isActive = false;
      this.menuContainer = menuContainer;
      this.allowSpaces = allowSpaces;
      this.replaceTextSuffix = replaceTextSuffix;
      this.positionMenu = positionMenu;
      this.hasTrailingSpace = false;
      this.spaceSelectsMatch = spaceSelectsMatch;

      if (this.autocompleteMode) {
        trigger = "";
        allowSpaces = false;
      }

      if (values) {
        this.collection = [{
          // symbol that starts the lookup
          trigger: trigger,
          // is it wrapped in an iframe
          iframe: iframe,
          // class applied to selected item
          selectClass: selectClass,
          // class applied to the Container
          containerClass: containerClass,
          // class applied to each item
          itemClass: itemClass,
          // function called on select that retuns the content to insert
          selectTemplate: (selectTemplate || Tribute.defaultSelectTemplate).bind(this),
          // function called that returns content for an item
          menuItemTemplate: (menuItemTemplate || Tribute.defaultMenuItemTemplate).bind(this),
          // function called when menu is empty, disables hiding of menu.
          noMatchTemplate: function (t) {
            if (typeof t === "string") {
              if (t.trim() === "") return null;
              return t;
            }

            if (typeof t === "function") {
              return t.bind(_this);
            }

            return noMatchTemplate || function () {
              return "<li>No Match Found!</li>";
            }.bind(_this);
          }(noMatchTemplate),
          // column to search against in the object
          lookup: lookup,
          // column that contains the content to insert by default
          fillAttr: fillAttr,
          // array of objects or a function returning an array of objects
          values: values,
          requireLeadingSpace: requireLeadingSpace,
          searchOpts: searchOpts,
          menuItemLimit: menuItemLimit,
          menuShowMinLength: menuShowMinLength
        }];
      } else if (collection) {
        if (this.autocompleteMode) console.warn("Tribute in autocomplete mode does not work for collections");
        this.collection = collection.map(function (item) {
          return {
            trigger: item.trigger || trigger,
            iframe: item.iframe || iframe,
            selectClass: item.selectClass || selectClass,
            containerClass: item.containerClass || containerClass,
            itemClass: item.itemClass || itemClass,
            selectTemplate: (item.selectTemplate || Tribute.defaultSelectTemplate).bind(_this),
            menuItemTemplate: (item.menuItemTemplate || Tribute.defaultMenuItemTemplate).bind(_this),
            // function called when menu is empty, disables hiding of menu.
            noMatchTemplate: function (t) {
              if (typeof t === "string") {
                if (t.trim() === "") return null;
                return t;
              }

              if (typeof t === "function") {
                return t.bind(_this);
              }

              return noMatchTemplate || function () {
                return "<li>No Match Found!</li>";
              }.bind(_this);
            }(noMatchTemplate),
            lookup: item.lookup || lookup,
            fillAttr: item.fillAttr || fillAttr,
            values: item.values,
            requireLeadingSpace: item.requireLeadingSpace,
            searchOpts: item.searchOpts || searchOpts,
            menuItemLimit: item.menuItemLimit || menuItemLimit,
            menuShowMinLength: item.menuShowMinLength || menuShowMinLength
          };
        });
      } else {
        throw new Error("[Tribute] No collection specified.");
      }

      new TributeRange(this);
      new TributeEvents(this);
      new TributeMenuEvents(this);
      new TributeSearch(this);
    }

    _createClass(Tribute, [{
      key: "triggers",
      value: function triggers() {
        return this.collection.map(function (config) {
          return config.trigger;
        });
      }
    }, {
      key: "attach",
      value: function attach(el) {
        if (!el) {
          throw new Error("[Tribute] Must pass in a DOM node or NodeList.");
        } // Check if it is a jQuery collection


        if (typeof jQuery !== "undefined" && el instanceof jQuery) {
          el = el.get();
        } // Is el an Array/Array-like object?


        if (el.constructor === NodeList || el.constructor === HTMLCollection || el.constructor === Array) {
          var length = el.length;

          for (var i = 0; i < length; ++i) {
            this._attach(el[i]);
          }
        } else {
          this._attach(el);
        }
      }
    }, {
      key: "_attach",
      value: function _attach(el) {
        if (el.hasAttribute("data-tribute")) {
          console.warn("Tribute was already bound to " + el.nodeName);
        }

        this.ensureEditable(el);
        this.events.bind(el);
        el.setAttribute("data-tribute", true);
      }
    }, {
      key: "ensureEditable",
      value: function ensureEditable(element) {
        if (Tribute.inputTypes().indexOf(element.nodeName) === -1) {
          if (element.contentEditable) {
            element.contentEditable = true;
          } else {
            throw new Error("[Tribute] Cannot bind to " + element.nodeName);
          }
        }
      }
    }, {
      key: "createMenu",
      value: function createMenu(containerClass) {
        var wrapper = this.range.getDocument().createElement("div"),
            ul = this.range.getDocument().createElement("ul");
        wrapper.className = containerClass;
        wrapper.appendChild(ul);

        if (this.menuContainer) {
          return this.menuContainer.appendChild(wrapper);
        }

        return this.range.getDocument().body.appendChild(wrapper);
      }
    }, {
      key: "showMenuFor",
      value: function showMenuFor(element, scrollTo) {
        var _this2 = this;

        // Only proceed if menu isn't already shown for the current element & mentionText
        if (this.isActive && this.current.element === element && this.current.mentionText === this.currentMentionTextSnapshot) {
          return;
        }

        this.currentMentionTextSnapshot = this.current.mentionText; // create the menu if it doesn't exist.

        if (!this.menu) {
          this.menu = this.createMenu(this.current.collection.containerClass);
          element.tributeMenu = this.menu;
          this.menuEvents.bind(this.menu);
        }

        this.isActive = true;
        this.menuSelected = 0;

        if (!this.current.mentionText) {
          this.current.mentionText = "";
        }

        var processValues = function processValues(values) {
          // Tribute may not be active any more by the time the value callback returns
          if (!_this2.isActive) {
            return;
          }

          var items = _this2.search.filter(_this2.current.mentionText, values, {
            pre: _this2.current.collection.searchOpts.pre || "<span>",
            post: _this2.current.collection.searchOpts.post || "</span>",
            skip: _this2.current.collection.searchOpts.skip,
            extract: function extract(el) {
              if (typeof _this2.current.collection.lookup === "string") {
                return el[_this2.current.collection.lookup];
              } else if (typeof _this2.current.collection.lookup === "function") {
                return _this2.current.collection.lookup(el, _this2.current.mentionText);
              } else {
                throw new Error("Invalid lookup attribute, lookup must be string or function.");
              }
            }
          });

          if (_this2.current.collection.menuItemLimit) {
            items = items.slice(0, _this2.current.collection.menuItemLimit);
          }

          _this2.current.filteredItems = items;

          var ul = _this2.menu.querySelector("ul");

          _this2.range.positionMenuAtCaret(scrollTo);

          if (!items.length) {
            var noMatchEvent = new CustomEvent("tribute-no-match", {
              detail: _this2.menu
            });

            _this2.current.element.dispatchEvent(noMatchEvent);

            if (typeof _this2.current.collection.noMatchTemplate === "function" && !_this2.current.collection.noMatchTemplate() || !_this2.current.collection.noMatchTemplate) {
              _this2.hideMenu();
            } else {
              typeof _this2.current.collection.noMatchTemplate === "function" ? ul.innerHTML = _this2.current.collection.noMatchTemplate() : ul.innerHTML = _this2.current.collection.noMatchTemplate;
            }

            return;
          }

          ul.innerHTML = "";

          var fragment = _this2.range.getDocument().createDocumentFragment();

          items.forEach(function (item, index) {
            var li = _this2.range.getDocument().createElement("li");

            li.setAttribute("data-index", index);
            li.className = _this2.current.collection.itemClass;
            li.addEventListener("mousemove", function (e) {
              var _this2$_findLiTarget = _this2._findLiTarget(e.target),
                  _this2$_findLiTarget2 = _slicedToArray(_this2$_findLiTarget, 2),
                  li = _this2$_findLiTarget2[0],
                  index = _this2$_findLiTarget2[1];

              if (e.movementY !== 0) {
                _this2.events.setActiveLi(index);
              }
            });

            if (_this2.menuSelected === index) {
              li.classList.add(_this2.current.collection.selectClass);
            }

            li.innerHTML = _this2.current.collection.menuItemTemplate(item);
            fragment.appendChild(li);
          });
          ul.appendChild(fragment);
        };

        if (typeof this.current.collection.values === "function") {
          this.current.collection.values(this.current.mentionText, processValues);
        } else {
          processValues(this.current.collection.values);
        }
      }
    }, {
      key: "_findLiTarget",
      value: function _findLiTarget(el) {
        if (!el) return [];
        var index = el.getAttribute("data-index");
        return !index ? this._findLiTarget(el.parentNode) : [el, index];
      }
    }, {
      key: "showMenuForCollection",
      value: function showMenuForCollection(element, collectionIndex) {
        if (element !== document.activeElement) {
          this.placeCaretAtEnd(element);
        }

        this.current.collection = this.collection[collectionIndex || 0];
        this.current.externalTrigger = true;
        this.current.element = element;
        if (element.isContentEditable) this.insertTextAtCursor(this.current.collection.trigger);else this.insertAtCaret(element, this.current.collection.trigger);
        this.showMenuFor(element);
      } // TODO: make sure this works for inputs/textareas

    }, {
      key: "placeCaretAtEnd",
      value: function placeCaretAtEnd(el) {
        el.focus();

        if (typeof window.getSelection != "undefined" && typeof document.createRange != "undefined") {
          var range = document.createRange();
          range.selectNodeContents(el);
          range.collapse(false);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        } else if (typeof document.body.createTextRange != "undefined") {
          var textRange = document.body.createTextRange();
          textRange.moveToElementText(el);
          textRange.collapse(false);
          textRange.select();
        }
      } // for contenteditable

    }, {
      key: "insertTextAtCursor",
      value: function insertTextAtCursor(text) {
        var sel, range;
        sel = window.getSelection();
        range = sel.getRangeAt(0);
        range.deleteContents();
        var textNode = document.createTextNode(text);
        range.insertNode(textNode);
        range.selectNodeContents(textNode);
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);
      } // for regular inputs

    }, {
      key: "insertAtCaret",
      value: function insertAtCaret(textarea, text) {
        var scrollPos = textarea.scrollTop;
        var caretPos = textarea.selectionStart;
        var front = textarea.value.substring(0, caretPos);
        var back = textarea.value.substring(textarea.selectionEnd, textarea.value.length);
        textarea.value = front + text + back;
        caretPos = caretPos + text.length;
        textarea.selectionStart = caretPos;
        textarea.selectionEnd = caretPos;
        textarea.focus();
        textarea.scrollTop = scrollPos;
      }
    }, {
      key: "hideMenu",
      value: function hideMenu() {
        if (this.menu) {
          this.menu.style.cssText = "display: none;";
          this.isActive = false;
          this.menuSelected = 0;
          this.current = {};
        }
      }
    }, {
      key: "selectItemAtIndex",
      value: function selectItemAtIndex(index, originalEvent) {
        index = parseInt(index);
        if (typeof index !== "number" || isNaN(index)) return;
        var item = this.current.filteredItems[index];
        var content = this.current.collection.selectTemplate(item);
        if (content !== null) this.replaceText(content, originalEvent, item);
      }
    }, {
      key: "replaceText",
      value: function replaceText(content, originalEvent, item) {
        this.range.replaceTriggerText(content, true, true, originalEvent, item);
      }
    }, {
      key: "_append",
      value: function _append(collection, newValues, replace) {
        if (typeof collection.values === "function") {
          throw new Error("Unable to append to values, as it is a function.");
        } else if (!replace) {
          collection.values = collection.values.concat(newValues);
        } else {
          collection.values = newValues;
        }
      }
    }, {
      key: "append",
      value: function append(collectionIndex, newValues, replace) {
        var index = parseInt(collectionIndex);
        if (typeof index !== "number") throw new Error("please provide an index for the collection to update.");
        var collection = this.collection[index];

        this._append(collection, newValues, replace);
      }
    }, {
      key: "appendCurrent",
      value: function appendCurrent(newValues, replace) {
        if (this.isActive) {
          this._append(this.current.collection, newValues, replace);
        } else {
          throw new Error("No active state. Please use append instead and pass an index.");
        }
      }
    }, {
      key: "detach",
      value: function detach(el) {
        if (!el) {
          throw new Error("[Tribute] Must pass in a DOM node or NodeList.");
        } // Check if it is a jQuery collection


        if (typeof jQuery !== "undefined" && el instanceof jQuery) {
          el = el.get();
        } // Is el an Array/Array-like object?


        if (el.constructor === NodeList || el.constructor === HTMLCollection || el.constructor === Array) {
          var length = el.length;

          for (var i = 0; i < length; ++i) {
            this._detach(el[i]);
          }
        } else {
          this._detach(el);
        }
      }
    }, {
      key: "_detach",
      value: function _detach(el) {
        var _this3 = this;

        this.events.unbind(el);

        if (el.tributeMenu) {
          this.menuEvents.unbind(el.tributeMenu);
        }

        setTimeout(function () {
          el.removeAttribute("data-tribute");
          _this3.isActive = false;

          if (el.tributeMenu) {
            el.tributeMenu.remove();
          }
        });
      }
    }, {
      key: "isActive",
      get: function get() {
        return this._isActive;
      },
      set: function set(val) {
        if (this._isActive != val) {
          this._isActive = val;

          if (this.current.element) {
            var noMatchEvent = new CustomEvent("tribute-active-".concat(val));
            this.current.element.dispatchEvent(noMatchEvent);
          }
        }
      }
    }], [{
      key: "defaultSelectTemplate",
      value: function defaultSelectTemplate(item) {
        if (typeof item === "undefined") return "".concat(this.current.collection.trigger).concat(this.current.mentionText);

        if (this.range.isContentEditable(this.current.element)) {
          return '<span class="tribute-mention">' + (this.current.collection.trigger + item.original[this.current.collection.fillAttr]) + "</span>";
        }

        return this.current.collection.trigger + item.original[this.current.collection.fillAttr];
      }
    }, {
      key: "defaultMenuItemTemplate",
      value: function defaultMenuItemTemplate(matchItem) {
        return matchItem.string;
      }
    }, {
      key: "inputTypes",
      value: function inputTypes() {
        return ["TEXTAREA", "INPUT"];
      }
    }]);

    return Tribute;
  }();

  /**
   * Tribute.js
   * Native ES6 JavaScript @mention Plugin
   **/

  return Tribute;

})));
