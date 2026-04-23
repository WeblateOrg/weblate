// Copyright © Michal Čihař <michal@weblate.org>
//
// SPDX-License-Identifier: GPL-3.0-or-later

// Usage:
//   new DateRangePicker(inputElement);

(() => {
  function getDaysOfWeek() {
    return [
      pgettext("Short name of day", "Su"),
      pgettext("Short name of day", "Mo"),
      pgettext("Short name of day", "Tu"),
      pgettext("Short name of day", "We"),
      pgettext("Short name of day", "Th"),
      pgettext("Short name of day", "Fr"),
      pgettext("Short name of day", "Sa"),
    ];
  }

  function getMonthNames() {
    return [
      pgettext("Short name of month", "Jan"),
      pgettext("Short name of month", "Feb"),
      pgettext("Short name of month", "Mar"),
      pgettext("Short name of month", "Apr"),
      pgettext("Short name of month", "May"),
      pgettext("Short name of month", "Jun"),
      pgettext("Short name of month", "Jul"),
      pgettext("Short name of month", "Aug"),
      pgettext("Short name of month", "Sep"),
      pgettext("Short name of month", "Oct"),
      pgettext("Short name of month", "Nov"),
      pgettext("Short name of month", "Dec"),
    ];
  }

  function startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function sameDay(a, b) {
    return (
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }

  function inRange(d, a, b) {
    const t = startOfDay(d).getTime();
    return t >= startOfDay(a).getTime() && t <= startOfDay(b).getTime();
  }

  function formatDate(d) {
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${mm}/${dd}/${d.getFullYear()}`;
  }

  function parseDate(s) {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s);
    if (!m) return null;
    const d = new Date(Number(m[3]), Number(m[1]) - 1, Number(m[2]));
    if (Number.isNaN(d.getTime())) return null;
    return d;
  }

  function daysInMonth(year, month) {
    return new Date(year, month + 1, 0).getDate();
  }

  function firstWeekday(year, month) {
    return new Date(year, month, 1).getDay();
  }

  function getPresetRanges() {
    const today = startOfDay(new Date());

    function offsetDays(base, n) {
      const d = new Date(base);
      d.setDate(d.getDate() + n);
      return d;
    }

    function startOfMonth(d) {
      return new Date(d.getFullYear(), d.getMonth(), 1);
    }

    function endOfMonth(d) {
      return new Date(d.getFullYear(), d.getMonth() + 1, 0);
    }

    function startOfYear(d) {
      return new Date(d.getFullYear(), 0, 1);
    }

    function endOfYear(d) {
      return new Date(d.getFullYear(), 11, 31);
    }

    const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const lastYear = new Date(today.getFullYear() - 1, 0, 1);

    return [
      { label: gettext("Today"), start: today, end: today },
      {
        label: gettext("Yesterday"),
        start: offsetDays(today, -1),
        end: offsetDays(today, -1),
      },
      {
        label: gettext("Last 7 days"),
        start: offsetDays(today, -6),
        end: today,
      },
      {
        label: gettext("Last 30 days"),
        start: offsetDays(today, -29),
        end: today,
      },
      {
        label: gettext("This month"),
        start: startOfMonth(today),
        end: endOfMonth(today),
      },
      {
        label: gettext("Last month"),
        start: startOfMonth(lastMonth),
        end: endOfMonth(lastMonth),
      },
      {
        label: gettext("This year"),
        start: startOfYear(today),
        end: endOfYear(today),
      },
      {
        label: gettext("Last year"),
        start: startOfYear(lastYear),
        end: endOfYear(lastYear),
      },
    ];
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === undefined || v === null) continue;
        if (k === "className") {
          node.className = v;
        } else if (k.startsWith("on")) {
          node.addEventListener(k.slice(2).toLowerCase(), v);
        } else {
          node.setAttribute(k, v);
        }
      }
    }
    if (children != null) {
      if (Array.isArray(children)) {
        for (const c of children) {
          if (c != null) {
            node.append(typeof c === "string" ? document.createTextNode(c) : c);
          }
        }
      } else if (typeof children === "string") {
        node.textContent = children;
      } else {
        node.append(children);
      }
    }
    return node;
  }

  const instances = new Set();

  function initDocumentListeners() {
    if (initDocumentListeners.done) return;
    initDocumentListeners.done = true;

    document.addEventListener("mousedown", (e) => {
      for (const picker of instances) {
        if (
          picker.isOpen() &&
          !picker.container.contains(e.target) &&
          e.target !== picker.input
        ) {
          picker.close();
        }
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        for (const picker of instances) {
          if (picker.isOpen()) {
            picker.close();
            picker.input.focus();
          }
        }
      }
    });
  }

  class DateRangePicker {
    /**
     * @param {HTMLInputElement} input
     */
    constructor(input) {
      this.input = input;

      /* Selection state */
      this.startDate = null;
      this.endDate = null;

      /* Calendar view state */
      const now = new Date();
      this.viewYear = now.getFullYear();
      this.viewMonth = now.getMonth();

      /* Read initial dates from data attributes (set by ChangesView) */
      const dsStart = input.getAttribute("data-start-date");
      const dsEnd = input.getAttribute("data-end-date");
      if (dsStart && dsEnd) {
        this.startDate = parseDate(dsStart);
        this.endDate = parseDate(dsEnd);
        if (this.startDate) {
          this.viewYear = this.startDate.getFullYear();
          this.viewMonth = this.startDate.getMonth();
        }
      }

      /* Build dropdown container */
      this.container = el("div", {
        className: "datepicker",
        role: "dialog",
        "aria-label": gettext("Select date range"),
      });
      this.container.style.display = "none";

      this._wrapper = el("div", { className: "datepicker-wrapper" });
      this._wrapper.append(this.container);
      this.input.parentNode.insertBefore(this._wrapper, this.input.nextSibling);

      /* Event listeners */
      this.input.addEventListener("click", () => this.toggle());
      this.input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          this.toggle();
        }
      });
      this.input.setAttribute("readonly", "");
      this.input.setAttribute("autocomplete", "off");

      instances.add(this);
      initDocumentListeners();

      this.render();
    }

    isOpen() {
      return this.container.style.display !== "none";
    }

    open() {
      this.container.style.display = "";
      this.render();
      this._positionDropdown();
    }

    close() {
      this.container.style.display = "none";
    }

    toggle() {
      if (this.isOpen()) {
        this.close();
      } else {
        this.open();
      }
    }

    /** Position the dropdown below the input, flipping up if needed. */
    _positionDropdown() {
      const rect = this.input.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      const dropdownHeight = this.container.offsetHeight;

      if (spaceBelow < dropdownHeight && rect.top > dropdownHeight) {
        this.container.classList.add("datepicker-above");
        this.container.classList.remove("datepicker-below");
      } else {
        this.container.classList.add("datepicker-below");
        this.container.classList.remove("datepicker-above");
      }
    }

    /** Apply the current selection and close. */
    apply() {
      if (this.startDate && this.endDate) {
        this.input.value = `${formatDate(this.startDate)} - ${formatDate(this.endDate)}`;
      }
      this.close();
    }

    /** Clear selection and input value. */
    clear() {
      this.startDate = null;
      this.endDate = null;
      this.input.value = "";
      this.close();
    }

    /** Select a preset range. */
    selectPreset(start, end) {
      this.startDate = start;
      this.endDate = end;
      this.viewYear = start.getFullYear();
      this.viewMonth = start.getMonth();
      this.apply();
    }

    /** Handle a day cell click. */
    selectDay(date) {
      if (!this.startDate || this.endDate) {
        /* First click or re-selecting after a complete range. */
        this.startDate = date;
        this.endDate = null;
      } else {
        /* Second click — finalize range. */
        if (date < this.startDate) {
          this.endDate = this.startDate;
          this.startDate = date;
        } else {
          this.endDate = date;
        }
      }
      this.render();
    }

    prevMonth() {
      this.viewMonth -= 1;
      if (this.viewMonth < 0) {
        this.viewMonth = 11;
        this.viewYear -= 1;
      }
      this.render();
    }

    nextMonth() {
      this.viewMonth += 1;
      if (this.viewMonth > 11) {
        this.viewMonth = 0;
        this.viewYear += 1;
      }
      this.render();
    }

    render() {
      this.container.textContent = "";
      this.container.append(this._buildContent());
    }

    _buildContent() {
      const body = el("div", { className: "datepicker-body" }, [
        this._buildPresets(),
        this._buildCalendarPane(),
      ]);
      return el("div", { className: "datepicker-inner" }, [
        body,
        this._buildFooter(),
      ]);
    }

    _buildPresets() {
      const items = getPresetRanges().map((preset) => {
        const isActive =
          this.startDate &&
          this.endDate &&
          sameDay(this.startDate, preset.start) &&
          sameDay(this.endDate, preset.end);

        return el(
          "button",
          {
            type: "button",
            className: `datepicker-preset${isActive ? " active" : ""}`,
            onClick: () => this.selectPreset(preset.start, preset.end),
          },
          preset.label,
        );
      });

      return el("div", { className: "datepicker-presets" }, items);
    }

    _buildCalendarPane() {
      const monthNames = getMonthNames();
      const daysOfWeek = getDaysOfWeek();

      /* Header: prev / month-year / next */
      const header = el("div", { className: "datepicker-cal-header" }, [
        el(
          "button",
          {
            type: "button",
            className: "datepicker-nav",
            "aria-label": gettext("Previous month"),
            onClick: () => this.prevMonth(),
          },
          "\u2039" /* ‹ */,
        ),
        el(
          "span",
          { className: "datepicker-cal-title" },
          `${monthNames[this.viewMonth]} ${this.viewYear}`,
        ),
        el(
          "button",
          {
            type: "button",
            className: "datepicker-nav",
            "aria-label": gettext("Next month"),
            onClick: () => this.nextMonth(),
          },
          "\u203A" /* › */,
        ),
      ]);

      /* Weekday labels */
      const weekRow = el(
        "div",
        { className: "datepicker-weekdays" },
        daysOfWeek.map((d) =>
          el("span", { className: "datepicker-wdlabel" }, d),
        ),
      );

      /* Day grid */
      const grid = this._buildDayGrid();

      return el("div", { className: "datepicker-calendar" }, [
        header,
        weekRow,
        grid,
      ]);
    }

    _buildDayGrid() {
      const today = startOfDay(new Date());
      const totalDays = daysInMonth(this.viewYear, this.viewMonth);
      const startWd = firstWeekday(this.viewYear, this.viewMonth);
      const cells = [];

      /* Leading blanks */
      for (let i = 0; i < startWd; i++) {
        cells.push(
          el("span", { className: "datepicker-day datepicker-day--empty" }),
        );
      }

      for (let d = 1; d <= totalDays; d++) {
        const date = new Date(this.viewYear, this.viewMonth, d);
        const classes = ["datepicker-day"];

        if (sameDay(date, today)) {
          classes.push("datepicker-day--today");
        }

        /* Highlight states */
        const hasStart = this.startDate != null;
        const hasEnd = this.endDate != null;

        if (hasStart && sameDay(date, this.startDate)) {
          classes.push("datepicker-day--start");
        }
        if (hasEnd && sameDay(date, this.endDate)) {
          classes.push("datepicker-day--end");
        }
        if (hasStart && hasEnd && inRange(date, this.startDate, this.endDate)) {
          classes.push("datepicker-day--in-range");
        }

        const btn = el(
          "button",
          {
            type: "button",
            className: classes.join(" "),
            "aria-label": formatDate(date),
            onClick: () => this.selectDay(date),
          },
          String(d),
        );

        cells.push(btn);
      }

      return el("div", { className: "datepicker-days" }, cells);
    }

    _buildFooter() {
      const rangeText =
        this.startDate && this.endDate
          ? `${formatDate(this.startDate)} - ${formatDate(this.endDate)}`
          : this.startDate
            ? formatDate(this.startDate)
            : "";

      return el("div", { className: "datepicker-footer" }, [
        el("span", { className: "datepicker-footer-range" }, rangeText),
        el("div", { className: "datepicker-footer-btns" }, [
          el(
            "button",
            {
              type: "button",
              className: "btn btn-sm btn-warning datepicker-btn-clear",
              onClick: () => this.clear(),
            },
            gettext("Clear"),
          ),
          el(
            "button",
            {
              type: "button",
              className: "btn btn-sm btn-primary datepicker-btn-apply",
              disabled: !(this.startDate && this.endDate) ? "" : undefined,
              onClick: () => this.apply(),
            },
            gettext("Apply"),
          ),
        ]),
      ]);
    }
  }

  window.DateRangePicker = DateRangePicker;
})();
