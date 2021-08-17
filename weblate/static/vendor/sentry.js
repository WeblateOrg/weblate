/*! @sentry/browser 6.11.0 (948b9ad) | https://github.com/getsentry/sentry-javascript */
var Sentry = (function (exports) {
    /*! *****************************************************************************
    Copyright (c) Microsoft Corporation. All rights reserved.
    Licensed under the Apache License, Version 2.0 (the "License"); you may not use
    this file except in compliance with the License. You may obtain a copy of the
    License at http://www.apache.org/licenses/LICENSE-2.0

    THIS CODE IS PROVIDED ON AN *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
    KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION ANY IMPLIED
    WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A PARTICULAR PURPOSE,
    MERCHANTABLITY OR NON-INFRINGEMENT.

    See the Apache Version 2.0 License for specific language governing permissions
    and limitations under the License.
    ***************************************************************************** */
    /* global Reflect, Promise */

    var extendStatics = function(d, b) {
        extendStatics = Object.setPrototypeOf ||
            ({ __proto__: [] } instanceof Array && function (d, b) { d.__proto__ = b; }) ||
            function (d, b) { for (var p in b) if (b.hasOwnProperty(p)) d[p] = b[p]; };
        return extendStatics(d, b);
    };

    function __extends(d, b) {
        extendStatics(d, b);
        function __() { this.constructor = d; }
        d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
    }

    var __assign = function() {
        __assign = Object.assign || function __assign(t) {
            for (var s, i = 1, n = arguments.length; i < n; i++) {
                s = arguments[i];
                for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
            }
            return t;
        };
        return __assign.apply(this, arguments);
    };

    function __rest(s, e) {
        var t = {};
        for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
            t[p] = s[p];
        if (s != null && typeof Object.getOwnPropertySymbols === "function")
            for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) if (e.indexOf(p[i]) < 0)
                t[p[i]] = s[p[i]];
        return t;
    }

    function __values(o) {
        var m = typeof Symbol === "function" && o[Symbol.iterator], i = 0;
        if (m) return m.call(o);
        return {
            next: function () {
                if (o && i >= o.length) o = void 0;
                return { value: o && o[i++], done: !o };
            }
        };
    }

    function __read(o, n) {
        var m = typeof Symbol === "function" && o[Symbol.iterator];
        if (!m) return o;
        var i = m.call(o), r, ar = [], e;
        try {
            while ((n === void 0 || n-- > 0) && !(r = i.next()).done) ar.push(r.value);
        }
        catch (error) { e = { error: error }; }
        finally {
            try {
                if (r && !r.done && (m = i["return"])) m.call(i);
            }
            finally { if (e) throw e.error; }
        }
        return ar;
    }

    function __spread() {
        for (var ar = [], i = 0; i < arguments.length; i++)
            ar = ar.concat(__read(arguments[i]));
        return ar;
    }

    /** Console logging verbosity for the SDK. */
    var LogLevel;
    (function (LogLevel) {
        /** No logs will be generated. */
        LogLevel[LogLevel["None"] = 0] = "None";
        /** Only SDK internal errors will be logged. */
        LogLevel[LogLevel["Error"] = 1] = "Error";
        /** Information useful for debugging the SDK will be logged. */
        LogLevel[LogLevel["Debug"] = 2] = "Debug";
        /** All SDK actions will be logged. */
        LogLevel[LogLevel["Verbose"] = 3] = "Verbose";
    })(LogLevel || (LogLevel = {}));

    /**
     * Session Status
     */
    var SessionStatus;
    (function (SessionStatus) {
        /** JSDoc */
        SessionStatus["Ok"] = "ok";
        /** JSDoc */
        SessionStatus["Exited"] = "exited";
        /** JSDoc */
        SessionStatus["Crashed"] = "crashed";
        /** JSDoc */
        SessionStatus["Abnormal"] = "abnormal";
    })(SessionStatus || (SessionStatus = {}));
    var RequestSessionStatus;
    (function (RequestSessionStatus) {
        /** JSDoc */
        RequestSessionStatus["Ok"] = "ok";
        /** JSDoc */
        RequestSessionStatus["Errored"] = "errored";
        /** JSDoc */
        RequestSessionStatus["Crashed"] = "crashed";
    })(RequestSessionStatus || (RequestSessionStatus = {}));

    /** JSDoc */
    (function (Severity) {
        /** JSDoc */
        Severity["Fatal"] = "fatal";
        /** JSDoc */
        Severity["Error"] = "error";
        /** JSDoc */
        Severity["Warning"] = "warning";
        /** JSDoc */
        Severity["Log"] = "log";
        /** JSDoc */
        Severity["Info"] = "info";
        /** JSDoc */
        Severity["Debug"] = "debug";
        /** JSDoc */
        Severity["Critical"] = "critical";
    })(exports.Severity || (exports.Severity = {}));
    // eslint-disable-next-line @typescript-eslint/no-namespace, import/export
    (function (Severity) {
        /**
         * Converts a string-based level into a {@link Severity}.
         *
         * @param level string representation of Severity
         * @returns Severity
         */
        function fromString(level) {
            switch (level) {
                case 'debug':
                    return Severity.Debug;
                case 'info':
                    return Severity.Info;
                case 'warn':
                case 'warning':
                    return Severity.Warning;
                case 'error':
                    return Severity.Error;
                case 'fatal':
                    return Severity.Fatal;
                case 'critical':
                    return Severity.Critical;
                case 'log':
                default:
                    return Severity.Log;
            }
        }
        Severity.fromString = fromString;
    })(exports.Severity || (exports.Severity = {}));

    /** The status of an event. */
    (function (Status) {
        /** The status could not be determined. */
        Status["Unknown"] = "unknown";
        /** The event was skipped due to configuration or callbacks. */
        Status["Skipped"] = "skipped";
        /** The event was sent to Sentry successfully. */
        Status["Success"] = "success";
        /** The client is currently rate limited and will try again later. */
        Status["RateLimit"] = "rate_limit";
        /** The event could not be processed. */
        Status["Invalid"] = "invalid";
        /** A server-side error ocurred during submission. */
        Status["Failed"] = "failed";
    })(exports.Status || (exports.Status = {}));
    // eslint-disable-next-line @typescript-eslint/no-namespace, import/export
    (function (Status) {
        /**
         * Converts a HTTP status code into a {@link Status}.
         *
         * @param code The HTTP response status code.
         * @returns The send status or {@link Status.Unknown}.
         */
        function fromHttpCode(code) {
            if (code >= 200 && code < 300) {
                return Status.Success;
            }
            if (code === 429) {
                return Status.RateLimit;
            }
            if (code >= 400 && code < 500) {
                return Status.Invalid;
            }
            if (code >= 500) {
                return Status.Failed;
            }
            return Status.Unknown;
        }
        Status.fromHttpCode = fromHttpCode;
    })(exports.Status || (exports.Status = {}));

    var TransactionSamplingMethod;
    (function (TransactionSamplingMethod) {
        TransactionSamplingMethod["Explicit"] = "explicitly_set";
        TransactionSamplingMethod["Sampler"] = "client_sampler";
        TransactionSamplingMethod["Rate"] = "client_rate";
        TransactionSamplingMethod["Inheritance"] = "inheritance";
    })(TransactionSamplingMethod || (TransactionSamplingMethod = {}));

    /* eslint-disable @typescript-eslint/no-explicit-any */
    /* eslint-disable @typescript-eslint/explicit-module-boundary-types */
    /**
     * Checks whether given value's type is one of a few Error or Error-like
     * {@link isError}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isError(wat) {
        switch (Object.prototype.toString.call(wat)) {
            case '[object Error]':
                return true;
            case '[object Exception]':
                return true;
            case '[object DOMException]':
                return true;
            default:
                return isInstanceOf(wat, Error);
        }
    }
    /**
     * Checks whether given value's type is ErrorEvent
     * {@link isErrorEvent}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isErrorEvent(wat) {
        return Object.prototype.toString.call(wat) === '[object ErrorEvent]';
    }
    /**
     * Checks whether given value's type is DOMError
     * {@link isDOMError}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isDOMError(wat) {
        return Object.prototype.toString.call(wat) === '[object DOMError]';
    }
    /**
     * Checks whether given value's type is DOMException
     * {@link isDOMException}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isDOMException(wat) {
        return Object.prototype.toString.call(wat) === '[object DOMException]';
    }
    /**
     * Checks whether given value's type is a string
     * {@link isString}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isString(wat) {
        return Object.prototype.toString.call(wat) === '[object String]';
    }
    /**
     * Checks whether given value's is a primitive (undefined, null, number, boolean, string, bigint, symbol)
     * {@link isPrimitive}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isPrimitive(wat) {
        return wat === null || (typeof wat !== 'object' && typeof wat !== 'function');
    }
    /**
     * Checks whether given value's type is an object literal
     * {@link isPlainObject}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isPlainObject(wat) {
        return Object.prototype.toString.call(wat) === '[object Object]';
    }
    /**
     * Checks whether given value's type is an Event instance
     * {@link isEvent}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isEvent(wat) {
        return typeof Event !== 'undefined' && isInstanceOf(wat, Event);
    }
    /**
     * Checks whether given value's type is an Element instance
     * {@link isElement}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isElement(wat) {
        return typeof Element !== 'undefined' && isInstanceOf(wat, Element);
    }
    /**
     * Checks whether given value's type is an regexp
     * {@link isRegExp}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isRegExp(wat) {
        return Object.prototype.toString.call(wat) === '[object RegExp]';
    }
    /**
     * Checks whether given value has a then function.
     * @param wat A value to be checked.
     */
    function isThenable(wat) {
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        return Boolean(wat && wat.then && typeof wat.then === 'function');
    }
    /**
     * Checks whether given value's type is a SyntheticEvent
     * {@link isSyntheticEvent}.
     *
     * @param wat A value to be checked.
     * @returns A boolean representing the result.
     */
    function isSyntheticEvent(wat) {
        return isPlainObject(wat) && 'nativeEvent' in wat && 'preventDefault' in wat && 'stopPropagation' in wat;
    }
    /**
     * Checks whether given value's type is an instance of provided constructor.
     * {@link isInstanceOf}.
     *
     * @param wat A value to be checked.
     * @param base A constructor to be used in a check.
     * @returns A boolean representing the result.
     */
    function isInstanceOf(wat, base) {
        try {
            return wat instanceof base;
        }
        catch (_e) {
            return false;
        }
    }

    /**
     * Given a child DOM element, returns a query-selector statement describing that
     * and its ancestors
     * e.g. [HTMLElement] => body > div > input#foo.btn[name=baz]
     * @returns generated DOM path
     */
    function htmlTreeAsString(elem, keyAttrs) {
        // try/catch both:
        // - accessing event.target (see getsentry/raven-js#838, #768)
        // - `htmlTreeAsString` because it's complex, and just accessing the DOM incorrectly
        // - can throw an exception in some circumstances.
        try {
            var currentElem = elem;
            var MAX_TRAVERSE_HEIGHT = 5;
            var MAX_OUTPUT_LEN = 80;
            var out = [];
            var height = 0;
            var len = 0;
            var separator = ' > ';
            var sepLength = separator.length;
            var nextStr = void 0;
            // eslint-disable-next-line no-plusplus
            while (currentElem && height++ < MAX_TRAVERSE_HEIGHT) {
                nextStr = _htmlElementAsString(currentElem, keyAttrs);
                // bail out if
                // - nextStr is the 'html' element
                // - the length of the string that would be created exceeds MAX_OUTPUT_LEN
                //   (ignore this limit if we are on the first iteration)
                if (nextStr === 'html' || (height > 1 && len + out.length * sepLength + nextStr.length >= MAX_OUTPUT_LEN)) {
                    break;
                }
                out.push(nextStr);
                len += nextStr.length;
                currentElem = currentElem.parentNode;
            }
            return out.reverse().join(separator);
        }
        catch (_oO) {
            return '<unknown>';
        }
    }
    /**
     * Returns a simple, query-selector representation of a DOM element
     * e.g. [HTMLElement] => input#foo.btn[name=baz]
     * @returns generated DOM path
     */
    function _htmlElementAsString(el, keyAttrs) {
        var _a, _b;
        var elem = el;
        var out = [];
        var className;
        var classes;
        var key;
        var attr;
        var i;
        if (!elem || !elem.tagName) {
            return '';
        }
        out.push(elem.tagName.toLowerCase());
        // Pairs of attribute keys defined in `serializeAttribute` and their values on element.
        var keyAttrPairs = ((_a = keyAttrs) === null || _a === void 0 ? void 0 : _a.length) ? keyAttrs.filter(function (keyAttr) { return elem.getAttribute(keyAttr); }).map(function (keyAttr) { return [keyAttr, elem.getAttribute(keyAttr)]; })
            : null;
        if ((_b = keyAttrPairs) === null || _b === void 0 ? void 0 : _b.length) {
            keyAttrPairs.forEach(function (keyAttrPair) {
                out.push("[" + keyAttrPair[0] + "=\"" + keyAttrPair[1] + "\"]");
            });
        }
        else {
            if (elem.id) {
                out.push("#" + elem.id);
            }
            // eslint-disable-next-line prefer-const
            className = elem.className;
            if (className && isString(className)) {
                classes = className.split(/\s+/);
                for (i = 0; i < classes.length; i++) {
                    out.push("." + classes[i]);
                }
            }
        }
        var allowedAttrs = ['type', 'name', 'title', 'alt'];
        for (i = 0; i < allowedAttrs.length; i++) {
            key = allowedAttrs[i];
            attr = elem.getAttribute(key);
            if (attr) {
                out.push("[" + key + "=\"" + attr + "\"]");
            }
        }
        return out.join('');
    }

    var setPrototypeOf = Object.setPrototypeOf || ({ __proto__: [] } instanceof Array ? setProtoOf : mixinProperties);
    /**
     * setPrototypeOf polyfill using __proto__
     */
    // eslint-disable-next-line @typescript-eslint/ban-types
    function setProtoOf(obj, proto) {
        // @ts-ignore __proto__ does not exist on obj
        obj.__proto__ = proto;
        return obj;
    }
    /**
     * setPrototypeOf polyfill using mixin
     */
    // eslint-disable-next-line @typescript-eslint/ban-types
    function mixinProperties(obj, proto) {
        for (var prop in proto) {
            // eslint-disable-next-line no-prototype-builtins
            if (!obj.hasOwnProperty(prop)) {
                // @ts-ignore typescript complains about indexing so we remove
                obj[prop] = proto[prop];
            }
        }
        return obj;
    }

    /** An error emitted by Sentry SDKs and related utilities. */
    var SentryError = /** @class */ (function (_super) {
        __extends(SentryError, _super);
        function SentryError(message) {
            var _newTarget = this.constructor;
            var _this = _super.call(this, message) || this;
            _this.message = message;
            _this.name = _newTarget.prototype.constructor.name;
            setPrototypeOf(_this, _newTarget.prototype);
            return _this;
        }
        return SentryError;
    }(Error));

    /** Regular expression used to parse a Dsn. */
    var DSN_REGEX = /^(?:(\w+):)\/\/(?:(\w+)(?::(\w+))?@)([\w.-]+)(?::(\d+))?\/(.+)/;
    /** Error message */
    var ERROR_MESSAGE = 'Invalid Dsn';
    /** The Sentry Dsn, identifying a Sentry instance and project. */
    var Dsn = /** @class */ (function () {
        /** Creates a new Dsn component */
        function Dsn(from) {
            if (typeof from === 'string') {
                this._fromString(from);
            }
            else {
                this._fromComponents(from);
            }
            this._validate();
        }
        /**
         * Renders the string representation of this Dsn.
         *
         * By default, this will render the public representation without the password
         * component. To get the deprecated private representation, set `withPassword`
         * to true.
         *
         * @param withPassword When set to true, the password will be included.
         */
        Dsn.prototype.toString = function (withPassword) {
            if (withPassword === void 0) { withPassword = false; }
            var _a = this, host = _a.host, path = _a.path, pass = _a.pass, port = _a.port, projectId = _a.projectId, protocol = _a.protocol, publicKey = _a.publicKey;
            return (protocol + "://" + publicKey + (withPassword && pass ? ":" + pass : '') +
                ("@" + host + (port ? ":" + port : '') + "/" + (path ? path + "/" : path) + projectId));
        };
        /** Parses a string into this Dsn. */
        Dsn.prototype._fromString = function (str) {
            var match = DSN_REGEX.exec(str);
            if (!match) {
                throw new SentryError(ERROR_MESSAGE);
            }
            var _a = __read(match.slice(1), 6), protocol = _a[0], publicKey = _a[1], _b = _a[2], pass = _b === void 0 ? '' : _b, host = _a[3], _c = _a[4], port = _c === void 0 ? '' : _c, lastPath = _a[5];
            var path = '';
            var projectId = lastPath;
            var split = projectId.split('/');
            if (split.length > 1) {
                path = split.slice(0, -1).join('/');
                projectId = split.pop();
            }
            if (projectId) {
                var projectMatch = projectId.match(/^\d+/);
                if (projectMatch) {
                    projectId = projectMatch[0];
                }
            }
            this._fromComponents({ host: host, pass: pass, path: path, projectId: projectId, port: port, protocol: protocol, publicKey: publicKey });
        };
        /** Maps Dsn components into this instance. */
        Dsn.prototype._fromComponents = function (components) {
            // TODO this is for backwards compatibility, and can be removed in a future version
            if ('user' in components && !('publicKey' in components)) {
                components.publicKey = components.user;
            }
            this.user = components.publicKey || '';
            this.protocol = components.protocol;
            this.publicKey = components.publicKey || '';
            this.pass = components.pass || '';
            this.host = components.host;
            this.port = components.port || '';
            this.path = components.path || '';
            this.projectId = components.projectId;
        };
        /** Validates this Dsn and throws on error. */
        Dsn.prototype._validate = function () {
            var _this = this;
            ['protocol', 'publicKey', 'host', 'projectId'].forEach(function (component) {
                if (!_this[component]) {
                    throw new SentryError(ERROR_MESSAGE + ": " + component + " missing");
                }
            });
            if (!this.projectId.match(/^\d+$/)) {
                throw new SentryError(ERROR_MESSAGE + ": Invalid projectId " + this.projectId);
            }
            if (this.protocol !== 'http' && this.protocol !== 'https') {
                throw new SentryError(ERROR_MESSAGE + ": Invalid protocol " + this.protocol);
            }
            if (this.port && isNaN(parseInt(this.port, 10))) {
                throw new SentryError(ERROR_MESSAGE + ": Invalid port " + this.port);
            }
        };
        return Dsn;
    }());

    /**
     * Checks whether we're in the Node.js or Browser environment
     *
     * @returns Answer to given question
     */
    function isNodeEnv() {
        return Object.prototype.toString.call(typeof process !== 'undefined' ? process : 0) === '[object process]';
    }
    /**
     * Requires a module which is protected against bundler minification.
     *
     * @param request The module path to resolve
     */
    // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types, @typescript-eslint/no-explicit-any
    function dynamicRequire(mod, request) {
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        return mod.require(request);
    }

    /**
     * Truncates given string to the maximum characters count
     *
     * @param str An object that contains serializable values
     * @param max Maximum number of characters in truncated string (0 = unlimited)
     * @returns string Encoded
     */
    function truncate(str, max) {
        if (max === void 0) { max = 0; }
        if (typeof str !== 'string' || max === 0) {
            return str;
        }
        return str.length <= max ? str : str.substr(0, max) + "...";
    }
    /**
     * Join values in array
     * @param input array of values to be joined together
     * @param delimiter string to be placed in-between values
     * @returns Joined values
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function safeJoin(input, delimiter) {
        if (!Array.isArray(input)) {
            return '';
        }
        var output = [];
        // eslint-disable-next-line @typescript-eslint/prefer-for-of
        for (var i = 0; i < input.length; i++) {
            var value = input[i];
            try {
                output.push(String(value));
            }
            catch (e) {
                output.push('[value cannot be serialized]');
            }
        }
        return output.join(delimiter);
    }
    /**
     * Checks if the value matches a regex or includes the string
     * @param value The string value to be checked against
     * @param pattern Either a regex or a string that must be contained in value
     */
    function isMatchingPattern(value, pattern) {
        if (!isString(value)) {
            return false;
        }
        if (isRegExp(pattern)) {
            return pattern.test(value);
        }
        if (typeof pattern === 'string') {
            return value.indexOf(pattern) !== -1;
        }
        return false;
    }

    var fallbackGlobalObject = {};
    /**
     * Safely get global scope object
     *
     * @returns Global scope object
     */
    function getGlobalObject() {
        return (isNodeEnv()
            ? global
            : typeof window !== 'undefined'
                ? window
                : typeof self !== 'undefined'
                    ? self
                    : fallbackGlobalObject);
    }
    /**
     * UUID4 generator
     *
     * @returns string Generated UUID4.
     */
    function uuid4() {
        var global = getGlobalObject();
        var crypto = global.crypto || global.msCrypto;
        if (!(crypto === void 0) && crypto.getRandomValues) {
            // Use window.crypto API if available
            var arr = new Uint16Array(8);
            crypto.getRandomValues(arr);
            // set 4 in byte 7
            // eslint-disable-next-line no-bitwise
            arr[3] = (arr[3] & 0xfff) | 0x4000;
            // set 2 most significant bits of byte 9 to '10'
            // eslint-disable-next-line no-bitwise
            arr[4] = (arr[4] & 0x3fff) | 0x8000;
            var pad = function (num) {
                var v = num.toString(16);
                while (v.length < 4) {
                    v = "0" + v;
                }
                return v;
            };
            return (pad(arr[0]) + pad(arr[1]) + pad(arr[2]) + pad(arr[3]) + pad(arr[4]) + pad(arr[5]) + pad(arr[6]) + pad(arr[7]));
        }
        // http://stackoverflow.com/questions/105034/how-to-create-a-guid-uuid-in-javascript/2117523#2117523
        return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            // eslint-disable-next-line no-bitwise
            var r = (Math.random() * 16) | 0;
            // eslint-disable-next-line no-bitwise
            var v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }
    /**
     * Parses string form of URL into an object
     * // borrowed from https://tools.ietf.org/html/rfc3986#appendix-B
     * // intentionally using regex and not <a/> href parsing trick because React Native and other
     * // environments where DOM might not be available
     * @returns parsed URL object
     */
    function parseUrl(url) {
        if (!url) {
            return {};
        }
        var match = url.match(/^(([^:/?#]+):)?(\/\/([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?$/);
        if (!match) {
            return {};
        }
        // coerce to undefined values to empty string so we don't get 'undefined'
        var query = match[6] || '';
        var fragment = match[8] || '';
        return {
            host: match[4],
            path: match[5],
            protocol: match[2],
            relative: match[5] + query + fragment,
        };
    }
    /**
     * Extracts either message or type+value from an event that can be used for user-facing logs
     * @returns event's description
     */
    function getEventDescription(event) {
        if (event.message) {
            return event.message;
        }
        if (event.exception && event.exception.values && event.exception.values[0]) {
            var exception = event.exception.values[0];
            if (exception.type && exception.value) {
                return exception.type + ": " + exception.value;
            }
            return exception.type || exception.value || event.event_id || '<unknown>';
        }
        return event.event_id || '<unknown>';
    }
    /** JSDoc */
    function consoleSandbox(callback) {
        var global = getGlobalObject();
        var levels = ['debug', 'info', 'warn', 'error', 'log', 'assert'];
        if (!('console' in global)) {
            return callback();
        }
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        var originalConsole = global.console;
        var wrappedLevels = {};
        // Restore all wrapped console methods
        levels.forEach(function (level) {
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            if (level in global.console && originalConsole[level].__sentry_original__) {
                wrappedLevels[level] = originalConsole[level];
                originalConsole[level] = originalConsole[level].__sentry_original__;
            }
        });
        // Perform callback manipulations
        var result = callback();
        // Revert restoration to wrapped state
        Object.keys(wrappedLevels).forEach(function (level) {
            originalConsole[level] = wrappedLevels[level];
        });
        return result;
    }
    /**
     * Adds exception values, type and value to an synthetic Exception.
     * @param event The event to modify.
     * @param value Value of the exception.
     * @param type Type of the exception.
     * @hidden
     */
    function addExceptionTypeValue(event, value, type) {
        event.exception = event.exception || {};
        event.exception.values = event.exception.values || [];
        event.exception.values[0] = event.exception.values[0] || {};
        event.exception.values[0].value = event.exception.values[0].value || value || '';
        event.exception.values[0].type = event.exception.values[0].type || type || 'Error';
    }
    /**
     * Adds exception mechanism to a given event.
     * @param event The event to modify.
     * @param mechanism Mechanism of the mechanism.
     * @hidden
     */
    function addExceptionMechanism(event, mechanism) {
        if (mechanism === void 0) { mechanism = {}; }
        // TODO: Use real type with `keyof Mechanism` thingy and maybe make it better?
        try {
            // @ts-ignore Type 'Mechanism | {}' is not assignable to type 'Mechanism | undefined'
            // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
            event.exception.values[0].mechanism = event.exception.values[0].mechanism || {};
            Object.keys(mechanism).forEach(function (key) {
                // @ts-ignore Mechanism has no index signature
                // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
                event.exception.values[0].mechanism[key] = mechanism[key];
            });
        }
        catch (_oO) {
            // no-empty
        }
    }
    /**
     * A safe form of location.href
     */
    function getLocationHref() {
        try {
            return document.location.href;
        }
        catch (oO) {
            return '';
        }
    }
    var defaultRetryAfter = 60 * 1000; // 60 seconds
    /**
     * Extracts Retry-After value from the request header or returns default value
     * @param now current unix timestamp
     * @param header string representation of 'Retry-After' header
     */
    function parseRetryAfterHeader(now, header) {
        if (!header) {
            return defaultRetryAfter;
        }
        var headerDelay = parseInt("" + header, 10);
        if (!isNaN(headerDelay)) {
            return headerDelay * 1000;
        }
        var headerDate = Date.parse("" + header);
        if (!isNaN(headerDate)) {
            return headerDate - now;
        }
        return defaultRetryAfter;
    }

    /* eslint-disable @typescript-eslint/no-explicit-any */
    // TODO: Implement different loggers for different environments
    var global$1 = getGlobalObject();
    /** Prefix for logging strings */
    var PREFIX = 'Sentry Logger ';
    /** JSDoc */
    var Logger = /** @class */ (function () {
        /** JSDoc */
        function Logger() {
            this._enabled = false;
        }
        /** JSDoc */
        Logger.prototype.disable = function () {
            this._enabled = false;
        };
        /** JSDoc */
        Logger.prototype.enable = function () {
            this._enabled = true;
        };
        /** JSDoc */
        Logger.prototype.log = function () {
            var args = [];
            for (var _i = 0; _i < arguments.length; _i++) {
                args[_i] = arguments[_i];
            }
            if (!this._enabled) {
                return;
            }
            consoleSandbox(function () {
                global$1.console.log(PREFIX + "[Log]: " + args.join(' '));
            });
        };
        /** JSDoc */
        Logger.prototype.warn = function () {
            var args = [];
            for (var _i = 0; _i < arguments.length; _i++) {
                args[_i] = arguments[_i];
            }
            if (!this._enabled) {
                return;
            }
            consoleSandbox(function () {
                global$1.console.warn(PREFIX + "[Warn]: " + args.join(' '));
            });
        };
        /** JSDoc */
        Logger.prototype.error = function () {
            var args = [];
            for (var _i = 0; _i < arguments.length; _i++) {
                args[_i] = arguments[_i];
            }
            if (!this._enabled) {
                return;
            }
            consoleSandbox(function () {
                global$1.console.error(PREFIX + "[Error]: " + args.join(' '));
            });
        };
        return Logger;
    }());
    // Ensure we only have a single logger instance, even if multiple versions of @sentry/utils are being used
    global$1.__SENTRY__ = global$1.__SENTRY__ || {};
    var logger = global$1.__SENTRY__.logger || (global$1.__SENTRY__.logger = new Logger());

    /* eslint-disable @typescript-eslint/no-unsafe-member-access */
    /* eslint-disable @typescript-eslint/no-explicit-any */
    /* eslint-disable @typescript-eslint/explicit-module-boundary-types */
    /**
     * Memo class used for decycle json objects. Uses WeakSet if available otherwise array.
     */
    var Memo = /** @class */ (function () {
        function Memo() {
            this._hasWeakSet = typeof WeakSet === 'function';
            this._inner = this._hasWeakSet ? new WeakSet() : [];
        }
        /**
         * Sets obj to remember.
         * @param obj Object to remember
         */
        Memo.prototype.memoize = function (obj) {
            if (this._hasWeakSet) {
                if (this._inner.has(obj)) {
                    return true;
                }
                this._inner.add(obj);
                return false;
            }
            // eslint-disable-next-line @typescript-eslint/prefer-for-of
            for (var i = 0; i < this._inner.length; i++) {
                var value = this._inner[i];
                if (value === obj) {
                    return true;
                }
            }
            this._inner.push(obj);
            return false;
        };
        /**
         * Removes object from internal storage.
         * @param obj Object to forget
         */
        Memo.prototype.unmemoize = function (obj) {
            if (this._hasWeakSet) {
                this._inner.delete(obj);
            }
            else {
                for (var i = 0; i < this._inner.length; i++) {
                    if (this._inner[i] === obj) {
                        this._inner.splice(i, 1);
                        break;
                    }
                }
            }
        };
        return Memo;
    }());

    var defaultFunctionName = '<anonymous>';
    /**
     * Safely extract function name from itself
     */
    function getFunctionName(fn) {
        try {
            if (!fn || typeof fn !== 'function') {
                return defaultFunctionName;
            }
            return fn.name || defaultFunctionName;
        }
        catch (e) {
            // Just accessing custom props in some Selenium environments
            // can cause a "Permission denied" exception (see raven-js#495).
            return defaultFunctionName;
        }
    }

    /**
     * Replace a method in an object with a wrapped version of itself.
     *
     * @param source An object that contains a method to be wrapped.
     * @param name The name of the method to be wrapped.
     * @param replacementFactory A higher-order function that takes the original version of the given method and returns a
     * wrapped version. Note: The function returned by `replacementFactory` needs to be a non-arrow function, in order to
     * preserve the correct value of `this`, and the original method must be called using `origMethod.call(this, <other
     * args>)` or `origMethod.apply(this, [<other args>])` (rather than being called directly), again to preserve `this`.
     * @returns void
     */
    function fill(source, name, replacementFactory) {
        if (!(name in source)) {
            return;
        }
        var original = source[name];
        var wrapped = replacementFactory(original);
        // Make sure it's a function first, as we need to attach an empty prototype for `defineProperties` to work
        // otherwise it'll throw "TypeError: Object.defineProperties called on non-object"
        if (typeof wrapped === 'function') {
            try {
                wrapped.prototype = wrapped.prototype || {};
                Object.defineProperties(wrapped, {
                    __sentry_original__: {
                        enumerable: false,
                        value: original,
                    },
                });
            }
            catch (_Oo) {
                // This can throw if multiple fill happens on a global object like XMLHttpRequest
                // Fixes https://github.com/getsentry/sentry-javascript/issues/2043
            }
        }
        source[name] = wrapped;
    }
    /**
     * Encodes given object into url-friendly format
     *
     * @param object An object that contains serializable values
     * @returns string Encoded
     */
    function urlEncode(object) {
        return Object.keys(object)
            .map(function (key) { return encodeURIComponent(key) + "=" + encodeURIComponent(object[key]); })
            .join('&');
    }
    /**
     * Transforms any object into an object literal with all its attributes
     * attached to it.
     *
     * @param value Initial source that we have to transform in order for it to be usable by the serializer
     */
    function getWalkSource(value) {
        if (isError(value)) {
            var error = value;
            var err = {
                message: error.message,
                name: error.name,
                stack: error.stack,
            };
            for (var i in error) {
                if (Object.prototype.hasOwnProperty.call(error, i)) {
                    err[i] = error[i];
                }
            }
            return err;
        }
        if (isEvent(value)) {
            var event_1 = value;
            var source = {};
            // Accessing event attributes can throw (see https://github.com/getsentry/sentry-javascript/issues/768 and
            // https://github.com/getsentry/sentry-javascript/issues/838), but accessing `type` hasn't been wrapped in a
            // try-catch in at least two years and no one's complained, so that's likely not an issue anymore
            source.type = event_1.type;
            try {
                source.target = isElement(event_1.target)
                    ? htmlTreeAsString(event_1.target)
                    : Object.prototype.toString.call(event_1.target);
            }
            catch (_oO) {
                source.target = '<unknown>';
            }
            try {
                source.currentTarget = isElement(event_1.currentTarget)
                    ? htmlTreeAsString(event_1.currentTarget)
                    : Object.prototype.toString.call(event_1.currentTarget);
            }
            catch (_oO) {
                source.currentTarget = '<unknown>';
            }
            if (typeof CustomEvent !== 'undefined' && isInstanceOf(value, CustomEvent)) {
                source.detail = event_1.detail;
            }
            for (var attr in event_1) {
                if (Object.prototype.hasOwnProperty.call(event_1, attr)) {
                    source[attr] = event_1[attr];
                }
            }
            return source;
        }
        return value;
    }
    /** Calculates bytes size of input string */
    function utf8Length(value) {
        // eslint-disable-next-line no-bitwise
        return ~-encodeURI(value).split(/%..|./).length;
    }
    /** Calculates bytes size of input object */
    function jsonSize(value) {
        return utf8Length(JSON.stringify(value));
    }
    /** JSDoc */
    function normalizeToSize(object, 
    // Default Node.js REPL depth
    depth, 
    // 100kB, as 200kB is max payload size, so half sounds reasonable
    maxSize) {
        if (depth === void 0) { depth = 3; }
        if (maxSize === void 0) { maxSize = 100 * 1024; }
        var serialized = normalize(object, depth);
        if (jsonSize(serialized) > maxSize) {
            return normalizeToSize(object, depth - 1, maxSize);
        }
        return serialized;
    }
    /**
     * Transform any non-primitive, BigInt, or Symbol-type value into a string. Acts as a no-op on strings, numbers,
     * booleans, null, and undefined.
     *
     * @param value The value to stringify
     * @returns For non-primitive, BigInt, and Symbol-type values, a string denoting the value's type, type and value, or
     *  type and `description` property, respectively. For non-BigInt, non-Symbol primitives, returns the original value,
     *  unchanged.
     */
    function serializeValue(value) {
        var type = Object.prototype.toString.call(value);
        // Node.js REPL notation
        if (typeof value === 'string') {
            return value;
        }
        if (type === '[object Object]') {
            return '[Object]';
        }
        if (type === '[object Array]') {
            return '[Array]';
        }
        var normalized = normalizeValue(value);
        return isPrimitive(normalized) ? normalized : type;
    }
    /**
     * normalizeValue()
     *
     * Takes unserializable input and make it serializable friendly
     *
     * - translates undefined/NaN values to "[undefined]"/"[NaN]" respectively,
     * - serializes Error objects
     * - filter global objects
     */
    function normalizeValue(value, key) {
        if (key === 'domain' && value && typeof value === 'object' && value._events) {
            return '[Domain]';
        }
        if (key === 'domainEmitter') {
            return '[DomainEmitter]';
        }
        if (typeof global !== 'undefined' && value === global) {
            return '[Global]';
        }
        if (typeof window !== 'undefined' && value === window) {
            return '[Window]';
        }
        if (typeof document !== 'undefined' && value === document) {
            return '[Document]';
        }
        // React's SyntheticEvent thingy
        if (isSyntheticEvent(value)) {
            return '[SyntheticEvent]';
        }
        if (typeof value === 'number' && value !== value) {
            return '[NaN]';
        }
        if (value === void 0) {
            return '[undefined]';
        }
        if (typeof value === 'function') {
            return "[Function: " + getFunctionName(value) + "]";
        }
        // symbols and bigints are considered primitives by TS, but aren't natively JSON-serilaizable
        if (typeof value === 'symbol') {
            return "[" + String(value) + "]";
        }
        if (typeof value === 'bigint') {
            return "[BigInt: " + String(value) + "]";
        }
        return value;
    }
    /**
     * Walks an object to perform a normalization on it
     *
     * @param key of object that's walked in current iteration
     * @param value object to be walked
     * @param depth Optional number indicating how deep should walking be performed
     * @param memo Optional Memo class handling decycling
     */
    // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
    function walk(key, value, depth, memo) {
        if (depth === void 0) { depth = +Infinity; }
        if (memo === void 0) { memo = new Memo(); }
        // If we reach the maximum depth, serialize whatever has left
        if (depth === 0) {
            return serializeValue(value);
        }
        /* eslint-disable @typescript-eslint/no-unsafe-member-access */
        // If value implements `toJSON` method, call it and return early
        if (value !== null && value !== undefined && typeof value.toJSON === 'function') {
            return value.toJSON();
        }
        /* eslint-enable @typescript-eslint/no-unsafe-member-access */
        // If normalized value is a primitive, there are no branches left to walk, so we can just bail out, as theres no point in going down that branch any further
        var normalized = normalizeValue(value, key);
        if (isPrimitive(normalized)) {
            return normalized;
        }
        // Create source that we will use for next itterations, either objectified error object (Error type with extracted keys:value pairs) or the input itself
        var source = getWalkSource(value);
        // Create an accumulator that will act as a parent for all future itterations of that branch
        var acc = Array.isArray(value) ? [] : {};
        // If we already walked that branch, bail out, as it's circular reference
        if (memo.memoize(value)) {
            return '[Circular ~]';
        }
        // Walk all keys of the source
        for (var innerKey in source) {
            // Avoid iterating over fields in the prototype if they've somehow been exposed to enumeration.
            if (!Object.prototype.hasOwnProperty.call(source, innerKey)) {
                continue;
            }
            // Recursively walk through all the child nodes
            acc[innerKey] = walk(innerKey, source[innerKey], depth - 1, memo);
        }
        // Once walked through all the branches, remove the parent from memo storage
        memo.unmemoize(value);
        // Return accumulated values
        return acc;
    }
    /**
     * normalize()
     *
     * - Creates a copy to prevent original input mutation
     * - Skip non-enumerablers
     * - Calls `toJSON` if implemented
     * - Removes circular references
     * - Translates non-serializeable values (undefined/NaN/Functions) to serializable format
     * - Translates known global objects/Classes to a string representations
     * - Takes care of Error objects serialization
     * - Optionally limit depth of final output
     */
    // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
    function normalize(input, depth) {
        try {
            return JSON.parse(JSON.stringify(input, function (key, value) { return walk(key, value, depth); }));
        }
        catch (_oO) {
            return '**non-serializable**';
        }
    }
    /**
     * Given any captured exception, extract its keys and create a sorted
     * and truncated list that will be used inside the event message.
     * eg. `Non-error exception captured with keys: foo, bar, baz`
     */
    // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
    function extractExceptionKeysForMessage(exception, maxLength) {
        if (maxLength === void 0) { maxLength = 40; }
        var keys = Object.keys(getWalkSource(exception));
        keys.sort();
        if (!keys.length) {
            return '[object has no keys]';
        }
        if (keys[0].length >= maxLength) {
            return truncate(keys[0], maxLength);
        }
        for (var includedKeys = keys.length; includedKeys > 0; includedKeys--) {
            var serialized = keys.slice(0, includedKeys).join(', ');
            if (serialized.length > maxLength) {
                continue;
            }
            if (includedKeys === keys.length) {
                return serialized;
            }
            return truncate(serialized, maxLength);
        }
        return '';
    }
    /**
     * Given any object, return the new object with removed keys that value was `undefined`.
     * Works recursively on objects and arrays.
     */
    function dropUndefinedKeys(val) {
        var e_1, _a;
        if (isPlainObject(val)) {
            var obj = val;
            var rv = {};
            try {
                for (var _b = __values(Object.keys(obj)), _c = _b.next(); !_c.done; _c = _b.next()) {
                    var key = _c.value;
                    if (typeof obj[key] !== 'undefined') {
                        rv[key] = dropUndefinedKeys(obj[key]);
                    }
                }
            }
            catch (e_1_1) { e_1 = { error: e_1_1 }; }
            finally {
                try {
                    if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
                }
                finally { if (e_1) throw e_1.error; }
            }
            return rv;
        }
        if (Array.isArray(val)) {
            return val.map(dropUndefinedKeys);
        }
        return val;
    }

    /**
     * Tells whether current environment supports Fetch API
     * {@link supportsFetch}.
     *
     * @returns Answer to the given question.
     */
    function supportsFetch() {
        if (!('fetch' in getGlobalObject())) {
            return false;
        }
        try {
            new Headers();
            new Request('');
            new Response();
            return true;
        }
        catch (e) {
            return false;
        }
    }
    /**
     * isNativeFetch checks if the given function is a native implementation of fetch()
     */
    // eslint-disable-next-line @typescript-eslint/ban-types
    function isNativeFetch(func) {
        return func && /^function fetch\(\)\s+\{\s+\[native code\]\s+\}$/.test(func.toString());
    }
    /**
     * Tells whether current environment supports Fetch API natively
     * {@link supportsNativeFetch}.
     *
     * @returns true if `window.fetch` is natively implemented, false otherwise
     */
    function supportsNativeFetch() {
        if (!supportsFetch()) {
            return false;
        }
        var global = getGlobalObject();
        // Fast path to avoid DOM I/O
        // eslint-disable-next-line @typescript-eslint/unbound-method
        if (isNativeFetch(global.fetch)) {
            return true;
        }
        // window.fetch is implemented, but is polyfilled or already wrapped (e.g: by a chrome extension)
        // so create a "pure" iframe to see if that has native fetch
        var result = false;
        var doc = global.document;
        // eslint-disable-next-line deprecation/deprecation
        if (doc && typeof doc.createElement === "function") {
            try {
                var sandbox = doc.createElement('iframe');
                sandbox.hidden = true;
                doc.head.appendChild(sandbox);
                if (sandbox.contentWindow && sandbox.contentWindow.fetch) {
                    // eslint-disable-next-line @typescript-eslint/unbound-method
                    result = isNativeFetch(sandbox.contentWindow.fetch);
                }
                doc.head.removeChild(sandbox);
            }
            catch (err) {
                logger.warn('Could not create sandbox iframe for pure fetch check, bailing to window.fetch: ', err);
            }
        }
        return result;
    }
    /**
     * Tells whether current environment supports Referrer Policy API
     * {@link supportsReferrerPolicy}.
     *
     * @returns Answer to the given question.
     */
    function supportsReferrerPolicy() {
        // Despite all stars in the sky saying that Edge supports old draft syntax, aka 'never', 'always', 'origin' and 'default
        // https://caniuse.com/#feat=referrer-policy
        // It doesn't. And it throw exception instead of ignoring this parameter...
        // REF: https://github.com/getsentry/raven-js/issues/1233
        if (!supportsFetch()) {
            return false;
        }
        try {
            new Request('_', {
                referrerPolicy: 'origin',
            });
            return true;
        }
        catch (e) {
            return false;
        }
    }
    /**
     * Tells whether current environment supports History API
     * {@link supportsHistory}.
     *
     * @returns Answer to the given question.
     */
    function supportsHistory() {
        // NOTE: in Chrome App environment, touching history.pushState, *even inside
        //       a try/catch block*, will cause Chrome to output an error to console.error
        // borrowed from: https://github.com/angular/angular.js/pull/13945/files
        var global = getGlobalObject();
        /* eslint-disable @typescript-eslint/no-unsafe-member-access */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        var chrome = global.chrome;
        var isChromePackagedApp = chrome && chrome.app && chrome.app.runtime;
        /* eslint-enable @typescript-eslint/no-unsafe-member-access */
        var hasHistoryApi = 'history' in global && !!global.history.pushState && !!global.history.replaceState;
        return !isChromePackagedApp && hasHistoryApi;
    }

    var global$2 = getGlobalObject();
    /**
     * Instrument native APIs to call handlers that can be used to create breadcrumbs, APM spans etc.
     *  - Console API
     *  - Fetch API
     *  - XHR API
     *  - History API
     *  - DOM API (click/typing)
     *  - Error API
     *  - UnhandledRejection API
     */
    var handlers = {};
    var instrumented = {};
    /** Instruments given API */
    function instrument(type) {
        if (instrumented[type]) {
            return;
        }
        instrumented[type] = true;
        switch (type) {
            case 'console':
                instrumentConsole();
                break;
            case 'dom':
                instrumentDOM();
                break;
            case 'xhr':
                instrumentXHR();
                break;
            case 'fetch':
                instrumentFetch();
                break;
            case 'history':
                instrumentHistory();
                break;
            case 'error':
                instrumentError();
                break;
            case 'unhandledrejection':
                instrumentUnhandledRejection();
                break;
            default:
                logger.warn('unknown instrumentation type:', type);
        }
    }
    /**
     * Add handler that will be called when given type of instrumentation triggers.
     * Use at your own risk, this might break without changelog notice, only used internally.
     * @hidden
     */
    function addInstrumentationHandler(handler) {
        if (!handler || typeof handler.type !== 'string' || typeof handler.callback !== 'function') {
            return;
        }
        handlers[handler.type] = handlers[handler.type] || [];
        handlers[handler.type].push(handler.callback);
        instrument(handler.type);
    }
    /** JSDoc */
    function triggerHandlers(type, data) {
        var e_1, _a;
        if (!type || !handlers[type]) {
            return;
        }
        try {
            for (var _b = __values(handlers[type] || []), _c = _b.next(); !_c.done; _c = _b.next()) {
                var handler = _c.value;
                try {
                    handler(data);
                }
                catch (e) {
                    logger.error("Error while triggering instrumentation handler.\nType: " + type + "\nName: " + getFunctionName(handler) + "\nError: " + e);
                }
            }
        }
        catch (e_1_1) { e_1 = { error: e_1_1 }; }
        finally {
            try {
                if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
            }
            finally { if (e_1) throw e_1.error; }
        }
    }
    /** JSDoc */
    function instrumentConsole() {
        if (!('console' in global$2)) {
            return;
        }
        ['debug', 'info', 'warn', 'error', 'log', 'assert'].forEach(function (level) {
            if (!(level in global$2.console)) {
                return;
            }
            fill(global$2.console, level, function (originalConsoleLevel) {
                return function () {
                    var args = [];
                    for (var _i = 0; _i < arguments.length; _i++) {
                        args[_i] = arguments[_i];
                    }
                    triggerHandlers('console', { args: args, level: level });
                    // this fails for some browsers. :(
                    if (originalConsoleLevel) {
                        Function.prototype.apply.call(originalConsoleLevel, global$2.console, args);
                    }
                };
            });
        });
    }
    /** JSDoc */
    function instrumentFetch() {
        if (!supportsNativeFetch()) {
            return;
        }
        fill(global$2, 'fetch', function (originalFetch) {
            return function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                var handlerData = {
                    args: args,
                    fetchData: {
                        method: getFetchMethod(args),
                        url: getFetchUrl(args),
                    },
                    startTimestamp: Date.now(),
                };
                triggerHandlers('fetch', __assign({}, handlerData));
                // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                return originalFetch.apply(global$2, args).then(function (response) {
                    triggerHandlers('fetch', __assign(__assign({}, handlerData), { endTimestamp: Date.now(), response: response }));
                    return response;
                }, function (error) {
                    triggerHandlers('fetch', __assign(__assign({}, handlerData), { endTimestamp: Date.now(), error: error }));
                    // NOTE: If you are a Sentry user, and you are seeing this stack frame,
                    //       it means the sentry.javascript SDK caught an error invoking your application code.
                    //       This is expected behavior and NOT indicative of a bug with sentry.javascript.
                    throw error;
                });
            };
        });
    }
    /* eslint-disable @typescript-eslint/no-unsafe-member-access */
    /** Extract `method` from fetch call arguments */
    function getFetchMethod(fetchArgs) {
        if (fetchArgs === void 0) { fetchArgs = []; }
        if ('Request' in global$2 && isInstanceOf(fetchArgs[0], Request) && fetchArgs[0].method) {
            return String(fetchArgs[0].method).toUpperCase();
        }
        if (fetchArgs[1] && fetchArgs[1].method) {
            return String(fetchArgs[1].method).toUpperCase();
        }
        return 'GET';
    }
    /** Extract `url` from fetch call arguments */
    function getFetchUrl(fetchArgs) {
        if (fetchArgs === void 0) { fetchArgs = []; }
        if (typeof fetchArgs[0] === 'string') {
            return fetchArgs[0];
        }
        if ('Request' in global$2 && isInstanceOf(fetchArgs[0], Request)) {
            return fetchArgs[0].url;
        }
        return String(fetchArgs[0]);
    }
    /* eslint-enable @typescript-eslint/no-unsafe-member-access */
    /** JSDoc */
    function instrumentXHR() {
        if (!('XMLHttpRequest' in global$2)) {
            return;
        }
        // Poor man's implementation of ES6 `Map`, tracking and keeping in sync key and value separately.
        var requestKeys = [];
        var requestValues = [];
        var xhrproto = XMLHttpRequest.prototype;
        fill(xhrproto, 'open', function (originalOpen) {
            return function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                // eslint-disable-next-line @typescript-eslint/no-this-alias
                var xhr = this;
                var url = args[1];
                xhr.__sentry_xhr__ = {
                    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                    method: isString(args[0]) ? args[0].toUpperCase() : args[0],
                    url: args[1],
                };
                // if Sentry key appears in URL, don't capture it as a request
                // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                if (isString(url) && xhr.__sentry_xhr__.method === 'POST' && url.match(/sentry_key/)) {
                    xhr.__sentry_own_request__ = true;
                }
                var onreadystatechangeHandler = function () {
                    if (xhr.readyState === 4) {
                        try {
                            // touching statusCode in some platforms throws
                            // an exception
                            if (xhr.__sentry_xhr__) {
                                xhr.__sentry_xhr__.status_code = xhr.status;
                            }
                        }
                        catch (e) {
                            /* do nothing */
                        }
                        try {
                            var requestPos = requestKeys.indexOf(xhr);
                            if (requestPos !== -1) {
                                // Make sure to pop both key and value to keep it in sync.
                                requestKeys.splice(requestPos);
                                var args_1 = requestValues.splice(requestPos)[0];
                                if (xhr.__sentry_xhr__ && args_1[0] !== undefined) {
                                    xhr.__sentry_xhr__.body = args_1[0];
                                }
                            }
                        }
                        catch (e) {
                            /* do nothing */
                        }
                        triggerHandlers('xhr', {
                            args: args,
                            endTimestamp: Date.now(),
                            startTimestamp: Date.now(),
                            xhr: xhr,
                        });
                    }
                };
                if ('onreadystatechange' in xhr && typeof xhr.onreadystatechange === 'function') {
                    fill(xhr, 'onreadystatechange', function (original) {
                        return function () {
                            var readyStateArgs = [];
                            for (var _i = 0; _i < arguments.length; _i++) {
                                readyStateArgs[_i] = arguments[_i];
                            }
                            onreadystatechangeHandler();
                            return original.apply(xhr, readyStateArgs);
                        };
                    });
                }
                else {
                    xhr.addEventListener('readystatechange', onreadystatechangeHandler);
                }
                return originalOpen.apply(xhr, args);
            };
        });
        fill(xhrproto, 'send', function (originalSend) {
            return function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                requestKeys.push(this);
                requestValues.push(args);
                triggerHandlers('xhr', {
                    args: args,
                    startTimestamp: Date.now(),
                    xhr: this,
                });
                return originalSend.apply(this, args);
            };
        });
    }
    var lastHref;
    /** JSDoc */
    function instrumentHistory() {
        if (!supportsHistory()) {
            return;
        }
        var oldOnPopState = global$2.onpopstate;
        global$2.onpopstate = function () {
            var args = [];
            for (var _i = 0; _i < arguments.length; _i++) {
                args[_i] = arguments[_i];
            }
            var to = global$2.location.href;
            // keep track of the current URL state, as we always receive only the updated state
            var from = lastHref;
            lastHref = to;
            triggerHandlers('history', {
                from: from,
                to: to,
            });
            if (oldOnPopState) {
                // Apparently this can throw in Firefox when incorrectly implemented plugin is installed.
                // https://github.com/getsentry/sentry-javascript/issues/3344
                // https://github.com/bugsnag/bugsnag-js/issues/469
                try {
                    return oldOnPopState.apply(this, args);
                }
                catch (_oO) {
                    // no-empty
                }
            }
        };
        /** @hidden */
        function historyReplacementFunction(originalHistoryFunction) {
            return function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                var url = args.length > 2 ? args[2] : undefined;
                if (url) {
                    // coerce to string (this is what pushState does)
                    var from = lastHref;
                    var to = String(url);
                    // keep track of the current URL state, as we always receive only the updated state
                    lastHref = to;
                    triggerHandlers('history', {
                        from: from,
                        to: to,
                    });
                }
                return originalHistoryFunction.apply(this, args);
            };
        }
        fill(global$2.history, 'pushState', historyReplacementFunction);
        fill(global$2.history, 'replaceState', historyReplacementFunction);
    }
    var debounceDuration = 1000;
    var debounceTimerID;
    var lastCapturedEvent;
    /**
     * Decide whether the current event should finish the debounce of previously captured one.
     * @param previous previously captured event
     * @param current event to be captured
     */
    function shouldShortcircuitPreviousDebounce(previous, current) {
        // If there was no previous event, it should always be swapped for the new one.
        if (!previous) {
            return true;
        }
        // If both events have different type, then user definitely performed two separate actions. e.g. click + keypress.
        if (previous.type !== current.type) {
            return true;
        }
        try {
            // If both events have the same type, it's still possible that actions were performed on different targets.
            // e.g. 2 clicks on different buttons.
            if (previous.target !== current.target) {
                return true;
            }
        }
        catch (e) {
            // just accessing `target` property can throw an exception in some rare circumstances
            // see: https://github.com/getsentry/sentry-javascript/issues/838
        }
        // If both events have the same type _and_ same `target` (an element which triggered an event, _not necessarily_
        // to which an event listener was attached), we treat them as the same action, as we want to capture
        // only one breadcrumb. e.g. multiple clicks on the same button, or typing inside a user input box.
        return false;
    }
    /**
     * Decide whether an event should be captured.
     * @param event event to be captured
     */
    function shouldSkipDOMEvent(event) {
        // We are only interested in filtering `keypress` events for now.
        if (event.type !== 'keypress') {
            return false;
        }
        try {
            var target = event.target;
            if (!target || !target.tagName) {
                return true;
            }
            // Only consider keypress events on actual input elements. This will disregard keypresses targeting body
            // e.g.tabbing through elements, hotkeys, etc.
            if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
                return false;
            }
        }
        catch (e) {
            // just accessing `target` property can throw an exception in some rare circumstances
            // see: https://github.com/getsentry/sentry-javascript/issues/838
        }
        return true;
    }
    /**
     * Wraps addEventListener to capture UI breadcrumbs
     * @param handler function that will be triggered
     * @param globalListener indicates whether event was captured by the global event listener
     * @returns wrapped breadcrumb events handler
     * @hidden
     */
    function makeDOMEventHandler(handler, globalListener) {
        if (globalListener === void 0) { globalListener = false; }
        return function (event) {
            // It's possible this handler might trigger multiple times for the same
            // event (e.g. event propagation through node ancestors).
            // Ignore if we've already captured that event.
            if (!event || lastCapturedEvent === event) {
                return;
            }
            // We always want to skip _some_ events.
            if (shouldSkipDOMEvent(event)) {
                return;
            }
            var name = event.type === 'keypress' ? 'input' : event.type;
            // If there is no debounce timer, it means that we can safely capture the new event and store it for future comparisons.
            if (debounceTimerID === undefined) {
                handler({
                    event: event,
                    name: name,
                    global: globalListener,
                });
                lastCapturedEvent = event;
            }
            // If there is a debounce awaiting, see if the new event is different enough to treat it as a unique one.
            // If that's the case, emit the previous event and store locally the newly-captured DOM event.
            else if (shouldShortcircuitPreviousDebounce(lastCapturedEvent, event)) {
                handler({
                    event: event,
                    name: name,
                    global: globalListener,
                });
                lastCapturedEvent = event;
            }
            // Start a new debounce timer that will prevent us from capturing multiple events that should be grouped together.
            clearTimeout(debounceTimerID);
            debounceTimerID = global$2.setTimeout(function () {
                debounceTimerID = undefined;
            }, debounceDuration);
        };
    }
    /** JSDoc */
    function instrumentDOM() {
        if (!('document' in global$2)) {
            return;
        }
        // Make it so that any click or keypress that is unhandled / bubbled up all the way to the document triggers our dom
        // handlers. (Normally we have only one, which captures a breadcrumb for each click or keypress.) Do this before
        // we instrument `addEventListener` so that we don't end up attaching this handler twice.
        var triggerDOMHandler = triggerHandlers.bind(null, 'dom');
        var globalDOMEventHandler = makeDOMEventHandler(triggerDOMHandler, true);
        global$2.document.addEventListener('click', globalDOMEventHandler, false);
        global$2.document.addEventListener('keypress', globalDOMEventHandler, false);
        // After hooking into click and keypress events bubbled up to `document`, we also hook into user-handled
        // clicks & keypresses, by adding an event listener of our own to any element to which they add a listener. That
        // way, whenever one of their handlers is triggered, ours will be, too. (This is needed because their handler
        // could potentially prevent the event from bubbling up to our global listeners. This way, our handler are still
        // guaranteed to fire at least once.)
        ['EventTarget', 'Node'].forEach(function (target) {
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            var proto = global$2[target] && global$2[target].prototype;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access, no-prototype-builtins
            if (!proto || !proto.hasOwnProperty || !proto.hasOwnProperty('addEventListener')) {
                return;
            }
            fill(proto, 'addEventListener', function (originalAddEventListener) {
                return function (type, listener, options) {
                    if (type === 'click' || type == 'keypress') {
                        try {
                            var el = this;
                            var handlers_1 = (el.__sentry_instrumentation_handlers__ = el.__sentry_instrumentation_handlers__ || {});
                            var handlerForType = (handlers_1[type] = handlers_1[type] || { refCount: 0 });
                            if (!handlerForType.handler) {
                                var handler = makeDOMEventHandler(triggerDOMHandler);
                                handlerForType.handler = handler;
                                originalAddEventListener.call(this, type, handler, options);
                            }
                            handlerForType.refCount += 1;
                        }
                        catch (e) {
                            // Accessing dom properties is always fragile.
                            // Also allows us to skip `addEventListenrs` calls with no proper `this` context.
                        }
                    }
                    return originalAddEventListener.call(this, type, listener, options);
                };
            });
            fill(proto, 'removeEventListener', function (originalRemoveEventListener) {
                return function (type, listener, options) {
                    if (type === 'click' || type == 'keypress') {
                        try {
                            var el = this;
                            var handlers_2 = el.__sentry_instrumentation_handlers__ || {};
                            var handlerForType = handlers_2[type];
                            if (handlerForType) {
                                handlerForType.refCount -= 1;
                                // If there are no longer any custom handlers of the current type on this element, we can remove ours, too.
                                if (handlerForType.refCount <= 0) {
                                    originalRemoveEventListener.call(this, type, handlerForType.handler, options);
                                    handlerForType.handler = undefined;
                                    delete handlers_2[type]; // eslint-disable-line @typescript-eslint/no-dynamic-delete
                                }
                                // If there are no longer any custom handlers of any type on this element, cleanup everything.
                                if (Object.keys(handlers_2).length === 0) {
                                    delete el.__sentry_instrumentation_handlers__;
                                }
                            }
                        }
                        catch (e) {
                            // Accessing dom properties is always fragile.
                            // Also allows us to skip `addEventListenrs` calls with no proper `this` context.
                        }
                    }
                    return originalRemoveEventListener.call(this, type, listener, options);
                };
            });
        });
    }
    var _oldOnErrorHandler = null;
    /** JSDoc */
    function instrumentError() {
        _oldOnErrorHandler = global$2.onerror;
        global$2.onerror = function (msg, url, line, column, error) {
            triggerHandlers('error', {
                column: column,
                error: error,
                line: line,
                msg: msg,
                url: url,
            });
            if (_oldOnErrorHandler) {
                // eslint-disable-next-line prefer-rest-params
                return _oldOnErrorHandler.apply(this, arguments);
            }
            return false;
        };
    }
    var _oldOnUnhandledRejectionHandler = null;
    /** JSDoc */
    function instrumentUnhandledRejection() {
        _oldOnUnhandledRejectionHandler = global$2.onunhandledrejection;
        global$2.onunhandledrejection = function (e) {
            triggerHandlers('unhandledrejection', e);
            if (_oldOnUnhandledRejectionHandler) {
                // eslint-disable-next-line prefer-rest-params
                return _oldOnUnhandledRejectionHandler.apply(this, arguments);
            }
            return true;
        };
    }

    /* eslint-disable @typescript-eslint/explicit-function-return-type */
    /** SyncPromise internal states */
    var States;
    (function (States) {
        /** Pending */
        States["PENDING"] = "PENDING";
        /** Resolved / OK */
        States["RESOLVED"] = "RESOLVED";
        /** Rejected / Error */
        States["REJECTED"] = "REJECTED";
    })(States || (States = {}));
    /**
     * Thenable class that behaves like a Promise and follows it's interface
     * but is not async internally
     */
    var SyncPromise = /** @class */ (function () {
        function SyncPromise(executor) {
            var _this = this;
            this._state = States.PENDING;
            this._handlers = [];
            /** JSDoc */
            this._resolve = function (value) {
                _this._setResult(States.RESOLVED, value);
            };
            /** JSDoc */
            this._reject = function (reason) {
                _this._setResult(States.REJECTED, reason);
            };
            /** JSDoc */
            this._setResult = function (state, value) {
                if (_this._state !== States.PENDING) {
                    return;
                }
                if (isThenable(value)) {
                    void value.then(_this._resolve, _this._reject);
                    return;
                }
                _this._state = state;
                _this._value = value;
                _this._executeHandlers();
            };
            // TODO: FIXME
            /** JSDoc */
            this._attachHandler = function (handler) {
                _this._handlers = _this._handlers.concat(handler);
                _this._executeHandlers();
            };
            /** JSDoc */
            this._executeHandlers = function () {
                if (_this._state === States.PENDING) {
                    return;
                }
                var cachedHandlers = _this._handlers.slice();
                _this._handlers = [];
                cachedHandlers.forEach(function (handler) {
                    if (handler.done) {
                        return;
                    }
                    if (_this._state === States.RESOLVED) {
                        if (handler.onfulfilled) {
                            // eslint-disable-next-line @typescript-eslint/no-floating-promises
                            handler.onfulfilled(_this._value);
                        }
                    }
                    if (_this._state === States.REJECTED) {
                        if (handler.onrejected) {
                            handler.onrejected(_this._value);
                        }
                    }
                    handler.done = true;
                });
            };
            try {
                executor(this._resolve, this._reject);
            }
            catch (e) {
                this._reject(e);
            }
        }
        /** JSDoc */
        SyncPromise.resolve = function (value) {
            return new SyncPromise(function (resolve) {
                resolve(value);
            });
        };
        /** JSDoc */
        SyncPromise.reject = function (reason) {
            return new SyncPromise(function (_, reject) {
                reject(reason);
            });
        };
        /** JSDoc */
        SyncPromise.all = function (collection) {
            return new SyncPromise(function (resolve, reject) {
                if (!Array.isArray(collection)) {
                    reject(new TypeError("Promise.all requires an array as input."));
                    return;
                }
                if (collection.length === 0) {
                    resolve([]);
                    return;
                }
                var counter = collection.length;
                var resolvedCollection = [];
                collection.forEach(function (item, index) {
                    void SyncPromise.resolve(item)
                        .then(function (value) {
                        resolvedCollection[index] = value;
                        counter -= 1;
                        if (counter !== 0) {
                            return;
                        }
                        resolve(resolvedCollection);
                    })
                        .then(null, reject);
                });
            });
        };
        /** JSDoc */
        SyncPromise.prototype.then = function (onfulfilled, onrejected) {
            var _this = this;
            return new SyncPromise(function (resolve, reject) {
                _this._attachHandler({
                    done: false,
                    onfulfilled: function (result) {
                        if (!onfulfilled) {
                            // TODO: ¯\_(ツ)_/¯
                            // TODO: FIXME
                            resolve(result);
                            return;
                        }
                        try {
                            resolve(onfulfilled(result));
                            return;
                        }
                        catch (e) {
                            reject(e);
                            return;
                        }
                    },
                    onrejected: function (reason) {
                        if (!onrejected) {
                            reject(reason);
                            return;
                        }
                        try {
                            resolve(onrejected(reason));
                            return;
                        }
                        catch (e) {
                            reject(e);
                            return;
                        }
                    },
                });
            });
        };
        /** JSDoc */
        SyncPromise.prototype.catch = function (onrejected) {
            return this.then(function (val) { return val; }, onrejected);
        };
        /** JSDoc */
        SyncPromise.prototype.finally = function (onfinally) {
            var _this = this;
            return new SyncPromise(function (resolve, reject) {
                var val;
                var isRejected;
                return _this.then(function (value) {
                    isRejected = false;
                    val = value;
                    if (onfinally) {
                        onfinally();
                    }
                }, function (reason) {
                    isRejected = true;
                    val = reason;
                    if (onfinally) {
                        onfinally();
                    }
                }).then(function () {
                    if (isRejected) {
                        reject(val);
                        return;
                    }
                    resolve(val);
                });
            });
        };
        /** JSDoc */
        SyncPromise.prototype.toString = function () {
            return '[object SyncPromise]';
        };
        return SyncPromise;
    }());

    /** A simple queue that holds promises. */
    var PromiseBuffer = /** @class */ (function () {
        function PromiseBuffer(_limit) {
            this._limit = _limit;
            /** Internal set of queued Promises */
            this._buffer = [];
        }
        /**
         * Says if the buffer is ready to take more requests
         */
        PromiseBuffer.prototype.isReady = function () {
            return this._limit === undefined || this.length() < this._limit;
        };
        /**
         * Add a promise (representing an in-flight action) to the queue, and set it to remove itself on fulfillment.
         *
         * @param taskProducer A function producing any PromiseLike<T>; In previous versions this used to be `task:
         *        PromiseLike<T>`, but under that model, Promises were instantly created on the call-site and their executor
         *        functions therefore ran immediately. Thus, even if the buffer was full, the action still happened. By
         *        requiring the promise to be wrapped in a function, we can defer promise creation until after the buffer
         *        limit check.
         * @returns The original promise.
         */
        PromiseBuffer.prototype.add = function (taskProducer) {
            var _this = this;
            if (!this.isReady()) {
                return SyncPromise.reject(new SentryError('Not adding Promise due to buffer limit reached.'));
            }
            // start the task and add its promise to the queue
            var task = taskProducer();
            if (this._buffer.indexOf(task) === -1) {
                this._buffer.push(task);
            }
            void task
                .then(function () { return _this.remove(task); })
                // Use `then(null, rejectionHandler)` rather than `catch(rejectionHandler)` so that we can use `PromiseLike`
                // rather than `Promise`. `PromiseLike` doesn't have a `.catch` method, making its polyfill smaller. (ES5 didn't
                // have promises, so TS has to polyfill when down-compiling.)
                .then(null, function () {
                return _this.remove(task).then(null, function () {
                    // We have to add another catch here because `this.remove()` starts a new promise chain.
                });
            });
            return task;
        };
        /**
         * Remove a promise from the queue.
         *
         * @param task Can be any PromiseLike<T>
         * @returns Removed promise.
         */
        PromiseBuffer.prototype.remove = function (task) {
            var removedTask = this._buffer.splice(this._buffer.indexOf(task), 1)[0];
            return removedTask;
        };
        /**
         * This function returns the number of unresolved promises in the queue.
         */
        PromiseBuffer.prototype.length = function () {
            return this._buffer.length;
        };
        /**
         * Wait for all promises in the queue to resolve or for timeout to expire, whichever comes first.
         *
         * @param timeout The time, in ms, after which to resolve to `false` if the queue is still non-empty. Passing `0` (or
         * not passing anything) will make the promise wait as long as it takes for the queue to drain before resolving to
         * `true`.
         * @returns A promise which will resolve to `true` if the queue is already empty or drains before the timeout, and
         * `false` otherwise
         */
        PromiseBuffer.prototype.drain = function (timeout) {
            var _this = this;
            return new SyncPromise(function (resolve) {
                // wait for `timeout` ms and then resolve to `false` (if not cancelled first)
                var capturedSetTimeout = setTimeout(function () {
                    if (timeout && timeout > 0) {
                        resolve(false);
                    }
                }, timeout);
                // if all promises resolve in time, cancel the timer and resolve to `true`
                void SyncPromise.all(_this._buffer)
                    .then(function () {
                    clearTimeout(capturedSetTimeout);
                    resolve(true);
                })
                    .then(null, function () {
                    resolve(true);
                });
            });
        };
        return PromiseBuffer;
    }());

    /**
     * A TimestampSource implementation for environments that do not support the Performance Web API natively.
     *
     * Note that this TimestampSource does not use a monotonic clock. A call to `nowSeconds` may return a timestamp earlier
     * than a previously returned value. We do not try to emulate a monotonic behavior in order to facilitate debugging. It
     * is more obvious to explain "why does my span have negative duration" than "why my spans have zero duration".
     */
    var dateTimestampSource = {
        nowSeconds: function () { return Date.now() / 1000; },
    };
    /**
     * Returns a wrapper around the native Performance API browser implementation, or undefined for browsers that do not
     * support the API.
     *
     * Wrapping the native API works around differences in behavior from different browsers.
     */
    function getBrowserPerformance() {
        var performance = getGlobalObject().performance;
        if (!performance || !performance.now) {
            return undefined;
        }
        // Replace performance.timeOrigin with our own timeOrigin based on Date.now().
        //
        // This is a partial workaround for browsers reporting performance.timeOrigin such that performance.timeOrigin +
        // performance.now() gives a date arbitrarily in the past.
        //
        // Additionally, computing timeOrigin in this way fills the gap for browsers where performance.timeOrigin is
        // undefined.
        //
        // The assumption that performance.timeOrigin + performance.now() ~= Date.now() is flawed, but we depend on it to
        // interact with data coming out of performance entries.
        //
        // Note that despite recommendations against it in the spec, browsers implement the Performance API with a clock that
        // might stop when the computer is asleep (and perhaps under other circumstances). Such behavior causes
        // performance.timeOrigin + performance.now() to have an arbitrary skew over Date.now(). In laptop computers, we have
        // observed skews that can be as long as days, weeks or months.
        //
        // See https://github.com/getsentry/sentry-javascript/issues/2590.
        //
        // BUG: despite our best intentions, this workaround has its limitations. It mostly addresses timings of pageload
        // transactions, but ignores the skew built up over time that can aversely affect timestamps of navigation
        // transactions of long-lived web pages.
        var timeOrigin = Date.now() - performance.now();
        return {
            now: function () { return performance.now(); },
            timeOrigin: timeOrigin,
        };
    }
    /**
     * Returns the native Performance API implementation from Node.js. Returns undefined in old Node.js versions that don't
     * implement the API.
     */
    function getNodePerformance() {
        try {
            var perfHooks = dynamicRequire(module, 'perf_hooks');
            return perfHooks.performance;
        }
        catch (_) {
            return undefined;
        }
    }
    /**
     * The Performance API implementation for the current platform, if available.
     */
    var platformPerformance = isNodeEnv() ? getNodePerformance() : getBrowserPerformance();
    var timestampSource = platformPerformance === undefined
        ? dateTimestampSource
        : {
            nowSeconds: function () { return (platformPerformance.timeOrigin + platformPerformance.now()) / 1000; },
        };
    /**
     * Returns a timestamp in seconds since the UNIX epoch using the Date API.
     */
    var dateTimestampInSeconds = dateTimestampSource.nowSeconds.bind(dateTimestampSource);
    /**
     * Returns a timestamp in seconds since the UNIX epoch using either the Performance or Date APIs, depending on the
     * availability of the Performance API.
     *
     * See `usingPerformanceAPI` to test whether the Performance API is used.
     *
     * BUG: Note that because of how browsers implement the Performance API, the clock might stop when the computer is
     * asleep. This creates a skew between `dateTimestampInSeconds` and `timestampInSeconds`. The
     * skew can grow to arbitrary amounts like days, weeks or months.
     * See https://github.com/getsentry/sentry-javascript/issues/2590.
     */
    var timestampInSeconds = timestampSource.nowSeconds.bind(timestampSource);
    /**
     * The number of milliseconds since the UNIX epoch. This value is only usable in a browser, and only when the
     * performance API is available.
     */
    var browserPerformanceTimeOrigin = (function () {
        // Unfortunately browsers may report an inaccurate time origin data, through either performance.timeOrigin or
        // performance.timing.navigationStart, which results in poor results in performance data. We only treat time origin
        // data as reliable if they are within a reasonable threshold of the current time.
        var performance = getGlobalObject().performance;
        if (!performance || !performance.now) {
            return undefined;
        }
        var threshold = 3600 * 1000;
        var performanceNow = performance.now();
        var dateNow = Date.now();
        // if timeOrigin isn't available set delta to threshold so it isn't used
        var timeOriginDelta = performance.timeOrigin
            ? Math.abs(performance.timeOrigin + performanceNow - dateNow)
            : threshold;
        var timeOriginIsReliable = timeOriginDelta < threshold;
        // While performance.timing.navigationStart is deprecated in favor of performance.timeOrigin, performance.timeOrigin
        // is not as widely supported. Namely, performance.timeOrigin is undefined in Safari as of writing.
        // Also as of writing, performance.timing is not available in Web Workers in mainstream browsers, so it is not always
        // a valid fallback. In the absence of an initial time provided by the browser, fallback to the current time from the
        // Date API.
        // eslint-disable-next-line deprecation/deprecation
        var navigationStart = performance.timing && performance.timing.navigationStart;
        var hasNavigationStart = typeof navigationStart === 'number';
        // if navigationStart isn't available set delta to threshold so it isn't used
        var navigationStartDelta = hasNavigationStart ? Math.abs(navigationStart + performanceNow - dateNow) : threshold;
        var navigationStartIsReliable = navigationStartDelta < threshold;
        if (timeOriginIsReliable || navigationStartIsReliable) {
            // Use the more reliable time origin
            if (timeOriginDelta <= navigationStartDelta) {
                return performance.timeOrigin;
            }
            else {
                return navigationStart;
            }
        }
        return dateNow;
    })();

    /**
     * Absolute maximum number of breadcrumbs added to an event.
     * The `maxBreadcrumbs` option cannot be higher than this value.
     */
    var MAX_BREADCRUMBS = 100;
    /**
     * Holds additional event information. {@link Scope.applyToEvent} will be
     * called by the client before an event will be sent.
     */
    var Scope = /** @class */ (function () {
        function Scope() {
            /** Flag if notifying is happening. */
            this._notifyingListeners = false;
            /** Callback for client to receive scope changes. */
            this._scopeListeners = [];
            /** Callback list that will be called after {@link applyToEvent}. */
            this._eventProcessors = [];
            /** Array of breadcrumbs. */
            this._breadcrumbs = [];
            /** User */
            this._user = {};
            /** Tags */
            this._tags = {};
            /** Extra */
            this._extra = {};
            /** Contexts */
            this._contexts = {};
        }
        /**
         * Inherit values from the parent scope.
         * @param scope to clone.
         */
        Scope.clone = function (scope) {
            var newScope = new Scope();
            if (scope) {
                newScope._breadcrumbs = __spread(scope._breadcrumbs);
                newScope._tags = __assign({}, scope._tags);
                newScope._extra = __assign({}, scope._extra);
                newScope._contexts = __assign({}, scope._contexts);
                newScope._user = scope._user;
                newScope._level = scope._level;
                newScope._span = scope._span;
                newScope._session = scope._session;
                newScope._transactionName = scope._transactionName;
                newScope._fingerprint = scope._fingerprint;
                newScope._eventProcessors = __spread(scope._eventProcessors);
                newScope._requestSession = scope._requestSession;
            }
            return newScope;
        };
        /**
         * Add internal on change listener. Used for sub SDKs that need to store the scope.
         * @hidden
         */
        Scope.prototype.addScopeListener = function (callback) {
            this._scopeListeners.push(callback);
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.addEventProcessor = function (callback) {
            this._eventProcessors.push(callback);
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setUser = function (user) {
            this._user = user || {};
            if (this._session) {
                this._session.update({ user: user });
            }
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.getUser = function () {
            return this._user;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.getRequestSession = function () {
            return this._requestSession;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setRequestSession = function (requestSession) {
            this._requestSession = requestSession;
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setTags = function (tags) {
            this._tags = __assign(__assign({}, this._tags), tags);
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setTag = function (key, value) {
            var _a;
            this._tags = __assign(__assign({}, this._tags), (_a = {}, _a[key] = value, _a));
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setExtras = function (extras) {
            this._extra = __assign(__assign({}, this._extra), extras);
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setExtra = function (key, extra) {
            var _a;
            this._extra = __assign(__assign({}, this._extra), (_a = {}, _a[key] = extra, _a));
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setFingerprint = function (fingerprint) {
            this._fingerprint = fingerprint;
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setLevel = function (level) {
            this._level = level;
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setTransactionName = function (name) {
            this._transactionName = name;
            this._notifyScopeListeners();
            return this;
        };
        /**
         * Can be removed in major version.
         * @deprecated in favor of {@link this.setTransactionName}
         */
        Scope.prototype.setTransaction = function (name) {
            return this.setTransactionName(name);
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setContext = function (key, context) {
            var _a;
            if (context === null) {
                // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
                delete this._contexts[key];
            }
            else {
                this._contexts = __assign(__assign({}, this._contexts), (_a = {}, _a[key] = context, _a));
            }
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setSpan = function (span) {
            this._span = span;
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.getSpan = function () {
            return this._span;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.getTransaction = function () {
            var _a, _b, _c, _d;
            // often, this span will be a transaction, but it's not guaranteed to be
            var span = this.getSpan();
            // try it the new way first
            if ((_a = span) === null || _a === void 0 ? void 0 : _a.transaction) {
                return (_b = span) === null || _b === void 0 ? void 0 : _b.transaction;
            }
            // fallback to the old way (known bug: this only finds transactions with sampled = true)
            if ((_d = (_c = span) === null || _c === void 0 ? void 0 : _c.spanRecorder) === null || _d === void 0 ? void 0 : _d.spans[0]) {
                return span.spanRecorder.spans[0];
            }
            // neither way found a transaction
            return undefined;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.setSession = function (session) {
            if (!session) {
                delete this._session;
            }
            else {
                this._session = session;
            }
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.getSession = function () {
            return this._session;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.update = function (captureContext) {
            if (!captureContext) {
                return this;
            }
            if (typeof captureContext === 'function') {
                var updatedScope = captureContext(this);
                return updatedScope instanceof Scope ? updatedScope : this;
            }
            if (captureContext instanceof Scope) {
                this._tags = __assign(__assign({}, this._tags), captureContext._tags);
                this._extra = __assign(__assign({}, this._extra), captureContext._extra);
                this._contexts = __assign(__assign({}, this._contexts), captureContext._contexts);
                if (captureContext._user && Object.keys(captureContext._user).length) {
                    this._user = captureContext._user;
                }
                if (captureContext._level) {
                    this._level = captureContext._level;
                }
                if (captureContext._fingerprint) {
                    this._fingerprint = captureContext._fingerprint;
                }
                if (captureContext._requestSession) {
                    this._requestSession = captureContext._requestSession;
                }
            }
            else if (isPlainObject(captureContext)) {
                // eslint-disable-next-line no-param-reassign
                captureContext = captureContext;
                this._tags = __assign(__assign({}, this._tags), captureContext.tags);
                this._extra = __assign(__assign({}, this._extra), captureContext.extra);
                this._contexts = __assign(__assign({}, this._contexts), captureContext.contexts);
                if (captureContext.user) {
                    this._user = captureContext.user;
                }
                if (captureContext.level) {
                    this._level = captureContext.level;
                }
                if (captureContext.fingerprint) {
                    this._fingerprint = captureContext.fingerprint;
                }
                if (captureContext.requestSession) {
                    this._requestSession = captureContext.requestSession;
                }
            }
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.clear = function () {
            this._breadcrumbs = [];
            this._tags = {};
            this._extra = {};
            this._user = {};
            this._contexts = {};
            this._level = undefined;
            this._transactionName = undefined;
            this._fingerprint = undefined;
            this._requestSession = undefined;
            this._span = undefined;
            this._session = undefined;
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.addBreadcrumb = function (breadcrumb, maxBreadcrumbs) {
            var maxCrumbs = typeof maxBreadcrumbs === 'number' ? Math.min(maxBreadcrumbs, MAX_BREADCRUMBS) : MAX_BREADCRUMBS;
            // No data has been changed, so don't notify scope listeners
            if (maxCrumbs <= 0) {
                return this;
            }
            var mergedBreadcrumb = __assign({ timestamp: dateTimestampInSeconds() }, breadcrumb);
            this._breadcrumbs = __spread(this._breadcrumbs, [mergedBreadcrumb]).slice(-maxCrumbs);
            this._notifyScopeListeners();
            return this;
        };
        /**
         * @inheritDoc
         */
        Scope.prototype.clearBreadcrumbs = function () {
            this._breadcrumbs = [];
            this._notifyScopeListeners();
            return this;
        };
        /**
         * Applies the current context and fingerprint to the event.
         * Note that breadcrumbs will be added by the client.
         * Also if the event has already breadcrumbs on it, we do not merge them.
         * @param event Event
         * @param hint May contain additional information about the original exception.
         * @hidden
         */
        Scope.prototype.applyToEvent = function (event, hint) {
            var _a;
            if (this._extra && Object.keys(this._extra).length) {
                event.extra = __assign(__assign({}, this._extra), event.extra);
            }
            if (this._tags && Object.keys(this._tags).length) {
                event.tags = __assign(__assign({}, this._tags), event.tags);
            }
            if (this._user && Object.keys(this._user).length) {
                event.user = __assign(__assign({}, this._user), event.user);
            }
            if (this._contexts && Object.keys(this._contexts).length) {
                event.contexts = __assign(__assign({}, this._contexts), event.contexts);
            }
            if (this._level) {
                event.level = this._level;
            }
            if (this._transactionName) {
                event.transaction = this._transactionName;
            }
            // We want to set the trace context for normal events only if there isn't already
            // a trace context on the event. There is a product feature in place where we link
            // errors with transaction and it relies on that.
            if (this._span) {
                event.contexts = __assign({ trace: this._span.getTraceContext() }, event.contexts);
                var transactionName = (_a = this._span.transaction) === null || _a === void 0 ? void 0 : _a.name;
                if (transactionName) {
                    event.tags = __assign({ transaction: transactionName }, event.tags);
                }
            }
            this._applyFingerprint(event);
            event.breadcrumbs = __spread((event.breadcrumbs || []), this._breadcrumbs);
            event.breadcrumbs = event.breadcrumbs.length > 0 ? event.breadcrumbs : undefined;
            return this._notifyEventProcessors(__spread(getGlobalEventProcessors(), this._eventProcessors), event, hint);
        };
        /**
         * This will be called after {@link applyToEvent} is finished.
         */
        Scope.prototype._notifyEventProcessors = function (processors, event, hint, index) {
            var _this = this;
            if (index === void 0) { index = 0; }
            return new SyncPromise(function (resolve, reject) {
                var processor = processors[index];
                if (event === null || typeof processor !== 'function') {
                    resolve(event);
                }
                else {
                    var result = processor(__assign({}, event), hint);
                    if (isThenable(result)) {
                        void result
                            .then(function (final) { return _this._notifyEventProcessors(processors, final, hint, index + 1).then(resolve); })
                            .then(null, reject);
                    }
                    else {
                        void _this._notifyEventProcessors(processors, result, hint, index + 1)
                            .then(resolve)
                            .then(null, reject);
                    }
                }
            });
        };
        /**
         * This will be called on every set call.
         */
        Scope.prototype._notifyScopeListeners = function () {
            var _this = this;
            // We need this check for this._notifyingListeners to be able to work on scope during updates
            // If this check is not here we'll produce endless recursion when something is done with the scope
            // during the callback.
            if (!this._notifyingListeners) {
                this._notifyingListeners = true;
                this._scopeListeners.forEach(function (callback) {
                    callback(_this);
                });
                this._notifyingListeners = false;
            }
        };
        /**
         * Applies fingerprint from the scope to the event if there's one,
         * uses message if there's one instead or get rid of empty fingerprint
         */
        Scope.prototype._applyFingerprint = function (event) {
            // Make sure it's an array first and we actually have something in place
            event.fingerprint = event.fingerprint
                ? Array.isArray(event.fingerprint)
                    ? event.fingerprint
                    : [event.fingerprint]
                : [];
            // If we have something on the scope, then merge it with event
            if (this._fingerprint) {
                event.fingerprint = event.fingerprint.concat(this._fingerprint);
            }
            // If we have no data at all, remove empty array default
            if (event.fingerprint && !event.fingerprint.length) {
                delete event.fingerprint;
            }
        };
        return Scope;
    }());
    /**
     * Returns the global event processors.
     */
    function getGlobalEventProcessors() {
        /* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access  */
        var global = getGlobalObject();
        global.__SENTRY__ = global.__SENTRY__ || {};
        global.__SENTRY__.globalEventProcessors = global.__SENTRY__.globalEventProcessors || [];
        return global.__SENTRY__.globalEventProcessors;
        /* eslint-enable @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access */
    }
    /**
     * Add a EventProcessor to be kept globally.
     * @param callback EventProcessor to add
     */
    function addGlobalEventProcessor(callback) {
        getGlobalEventProcessors().push(callback);
    }

    /**
     * @inheritdoc
     */
    var Session = /** @class */ (function () {
        function Session(context) {
            this.errors = 0;
            this.sid = uuid4();
            this.duration = 0;
            this.status = SessionStatus.Ok;
            this.init = true;
            this.ignoreDuration = false;
            // Both timestamp and started are in seconds since the UNIX epoch.
            var startingTime = timestampInSeconds();
            this.timestamp = startingTime;
            this.started = startingTime;
            if (context) {
                this.update(context);
            }
        }
        /** JSDoc */
        // eslint-disable-next-line complexity
        Session.prototype.update = function (context) {
            if (context === void 0) { context = {}; }
            if (context.user) {
                if (!this.ipAddress && context.user.ip_address) {
                    this.ipAddress = context.user.ip_address;
                }
                if (!this.did && !context.did) {
                    this.did = context.user.id || context.user.email || context.user.username;
                }
            }
            this.timestamp = context.timestamp || timestampInSeconds();
            if (context.ignoreDuration) {
                this.ignoreDuration = context.ignoreDuration;
            }
            if (context.sid) {
                // Good enough uuid validation. — Kamil
                this.sid = context.sid.length === 32 ? context.sid : uuid4();
            }
            if (context.init !== undefined) {
                this.init = context.init;
            }
            if (!this.did && context.did) {
                this.did = "" + context.did;
            }
            if (typeof context.started === 'number') {
                this.started = context.started;
            }
            if (this.ignoreDuration) {
                this.duration = undefined;
            }
            else if (typeof context.duration === 'number') {
                this.duration = context.duration;
            }
            else {
                var duration = this.timestamp - this.started;
                this.duration = duration >= 0 ? duration : 0;
            }
            if (context.release) {
                this.release = context.release;
            }
            if (context.environment) {
                this.environment = context.environment;
            }
            if (!this.ipAddress && context.ipAddress) {
                this.ipAddress = context.ipAddress;
            }
            if (!this.userAgent && context.userAgent) {
                this.userAgent = context.userAgent;
            }
            if (typeof context.errors === 'number') {
                this.errors = context.errors;
            }
            if (context.status) {
                this.status = context.status;
            }
        };
        /** JSDoc */
        Session.prototype.close = function (status) {
            if (status) {
                this.update({ status: status });
            }
            else if (this.status === SessionStatus.Ok) {
                this.update({ status: SessionStatus.Exited });
            }
            else {
                this.update();
            }
        };
        /** JSDoc */
        Session.prototype.toJSON = function () {
            return dropUndefinedKeys({
                sid: "" + this.sid,
                init: this.init,
                // Make sure that sec is converted to ms for date constructor
                started: new Date(this.started * 1000).toISOString(),
                timestamp: new Date(this.timestamp * 1000).toISOString(),
                status: this.status,
                errors: this.errors,
                did: typeof this.did === 'number' || typeof this.did === 'string' ? "" + this.did : undefined,
                duration: this.duration,
                attrs: dropUndefinedKeys({
                    release: this.release,
                    environment: this.environment,
                    ip_address: this.ipAddress,
                    user_agent: this.userAgent,
                }),
            });
        };
        return Session;
    }());

    /**
     * API compatibility version of this hub.
     *
     * WARNING: This number should only be increased when the global interface
     * changes and new methods are introduced.
     *
     * @hidden
     */
    var API_VERSION = 4;
    /**
     * Default maximum number of breadcrumbs added to an event. Can be overwritten
     * with {@link Options.maxBreadcrumbs}.
     */
    var DEFAULT_BREADCRUMBS = 100;
    /**
     * @inheritDoc
     */
    var Hub = /** @class */ (function () {
        /**
         * Creates a new instance of the hub, will push one {@link Layer} into the
         * internal stack on creation.
         *
         * @param client bound to the hub.
         * @param scope bound to the hub.
         * @param version number, higher number means higher priority.
         */
        function Hub(client, scope, _version) {
            if (scope === void 0) { scope = new Scope(); }
            if (_version === void 0) { _version = API_VERSION; }
            this._version = _version;
            /** Is a {@link Layer}[] containing the client and scope */
            this._stack = [{}];
            this.getStackTop().scope = scope;
            if (client) {
                this.bindClient(client);
            }
        }
        /**
         * @inheritDoc
         */
        Hub.prototype.isOlderThan = function (version) {
            return this._version < version;
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.bindClient = function (client) {
            var top = this.getStackTop();
            top.client = client;
            if (client && client.setupIntegrations) {
                client.setupIntegrations();
            }
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.pushScope = function () {
            // We want to clone the content of prev scope
            var scope = Scope.clone(this.getScope());
            this.getStack().push({
                client: this.getClient(),
                scope: scope,
            });
            return scope;
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.popScope = function () {
            if (this.getStack().length <= 1)
                return false;
            return !!this.getStack().pop();
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.withScope = function (callback) {
            var scope = this.pushScope();
            try {
                callback(scope);
            }
            finally {
                this.popScope();
            }
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.getClient = function () {
            return this.getStackTop().client;
        };
        /** Returns the scope of the top stack. */
        Hub.prototype.getScope = function () {
            return this.getStackTop().scope;
        };
        /** Returns the scope stack for domains or the process. */
        Hub.prototype.getStack = function () {
            return this._stack;
        };
        /** Returns the topmost scope layer in the order domain > local > process. */
        Hub.prototype.getStackTop = function () {
            return this._stack[this._stack.length - 1];
        };
        /**
         * @inheritDoc
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
        Hub.prototype.captureException = function (exception, hint) {
            var eventId = (this._lastEventId = uuid4());
            var finalHint = hint;
            // If there's no explicit hint provided, mimic the same thing that would happen
            // in the minimal itself to create a consistent behavior.
            // We don't do this in the client, as it's the lowest level API, and doing this,
            // would prevent user from having full control over direct calls.
            if (!hint) {
                var syntheticException = void 0;
                try {
                    throw new Error('Sentry syntheticException');
                }
                catch (exception) {
                    syntheticException = exception;
                }
                finalHint = {
                    originalException: exception,
                    syntheticException: syntheticException,
                };
            }
            this._invokeClient('captureException', exception, __assign(__assign({}, finalHint), { event_id: eventId }));
            return eventId;
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.captureMessage = function (message, level, hint) {
            var eventId = (this._lastEventId = uuid4());
            var finalHint = hint;
            // If there's no explicit hint provided, mimic the same thing that would happen
            // in the minimal itself to create a consistent behavior.
            // We don't do this in the client, as it's the lowest level API, and doing this,
            // would prevent user from having full control over direct calls.
            if (!hint) {
                var syntheticException = void 0;
                try {
                    throw new Error(message);
                }
                catch (exception) {
                    syntheticException = exception;
                }
                finalHint = {
                    originalException: message,
                    syntheticException: syntheticException,
                };
            }
            this._invokeClient('captureMessage', message, level, __assign(__assign({}, finalHint), { event_id: eventId }));
            return eventId;
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.captureEvent = function (event, hint) {
            var eventId = (this._lastEventId = uuid4());
            this._invokeClient('captureEvent', event, __assign(__assign({}, hint), { event_id: eventId }));
            return eventId;
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.lastEventId = function () {
            return this._lastEventId;
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.addBreadcrumb = function (breadcrumb, hint) {
            var _a = this.getStackTop(), scope = _a.scope, client = _a.client;
            if (!scope || !client)
                return;
            // eslint-disable-next-line @typescript-eslint/unbound-method
            var _b = (client.getOptions && client.getOptions()) || {}, _c = _b.beforeBreadcrumb, beforeBreadcrumb = _c === void 0 ? null : _c, _d = _b.maxBreadcrumbs, maxBreadcrumbs = _d === void 0 ? DEFAULT_BREADCRUMBS : _d;
            if (maxBreadcrumbs <= 0)
                return;
            var timestamp = dateTimestampInSeconds();
            var mergedBreadcrumb = __assign({ timestamp: timestamp }, breadcrumb);
            var finalBreadcrumb = beforeBreadcrumb
                ? consoleSandbox(function () { return beforeBreadcrumb(mergedBreadcrumb, hint); })
                : mergedBreadcrumb;
            if (finalBreadcrumb === null)
                return;
            scope.addBreadcrumb(finalBreadcrumb, maxBreadcrumbs);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.setUser = function (user) {
            var scope = this.getScope();
            if (scope)
                scope.setUser(user);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.setTags = function (tags) {
            var scope = this.getScope();
            if (scope)
                scope.setTags(tags);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.setExtras = function (extras) {
            var scope = this.getScope();
            if (scope)
                scope.setExtras(extras);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.setTag = function (key, value) {
            var scope = this.getScope();
            if (scope)
                scope.setTag(key, value);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.setExtra = function (key, extra) {
            var scope = this.getScope();
            if (scope)
                scope.setExtra(key, extra);
        };
        /**
         * @inheritDoc
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Hub.prototype.setContext = function (name, context) {
            var scope = this.getScope();
            if (scope)
                scope.setContext(name, context);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.configureScope = function (callback) {
            var _a = this.getStackTop(), scope = _a.scope, client = _a.client;
            if (scope && client) {
                callback(scope);
            }
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.run = function (callback) {
            var oldHub = makeMain(this);
            try {
                callback(this);
            }
            finally {
                makeMain(oldHub);
            }
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.getIntegration = function (integration) {
            var client = this.getClient();
            if (!client)
                return null;
            try {
                return client.getIntegration(integration);
            }
            catch (_oO) {
                logger.warn("Cannot retrieve integration " + integration.id + " from the current Hub");
                return null;
            }
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.startSpan = function (context) {
            return this._callExtensionMethod('startSpan', context);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.startTransaction = function (context, customSamplingContext) {
            return this._callExtensionMethod('startTransaction', context, customSamplingContext);
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.traceHeaders = function () {
            return this._callExtensionMethod('traceHeaders');
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.captureSession = function (endSession) {
            if (endSession === void 0) { endSession = false; }
            // both send the update and pull the session from the scope
            if (endSession) {
                return this.endSession();
            }
            // only send the update
            this._sendSessionUpdate();
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.endSession = function () {
            var _a, _b, _c, _d, _e;
            (_c = (_b = (_a = this.getStackTop()) === null || _a === void 0 ? void 0 : _a.scope) === null || _b === void 0 ? void 0 : _b.getSession()) === null || _c === void 0 ? void 0 : _c.close();
            this._sendSessionUpdate();
            // the session is over; take it off of the scope
            (_e = (_d = this.getStackTop()) === null || _d === void 0 ? void 0 : _d.scope) === null || _e === void 0 ? void 0 : _e.setSession();
        };
        /**
         * @inheritDoc
         */
        Hub.prototype.startSession = function (context) {
            var _a = this.getStackTop(), scope = _a.scope, client = _a.client;
            var _b = (client && client.getOptions()) || {}, release = _b.release, environment = _b.environment;
            // Will fetch userAgent if called from browser sdk
            var global = getGlobalObject();
            var userAgent = (global.navigator || {}).userAgent;
            var session = new Session(__assign(__assign(__assign({ release: release,
                environment: environment }, (scope && { user: scope.getUser() })), (userAgent && { userAgent: userAgent })), context));
            if (scope) {
                // End existing session if there's one
                var currentSession = scope.getSession && scope.getSession();
                if (currentSession && currentSession.status === SessionStatus.Ok) {
                    currentSession.update({ status: SessionStatus.Exited });
                }
                this.endSession();
                // Afterwards we set the new session on the scope
                scope.setSession(session);
            }
            return session;
        };
        /**
         * Sends the current Session on the scope
         */
        Hub.prototype._sendSessionUpdate = function () {
            var _a = this.getStackTop(), scope = _a.scope, client = _a.client;
            if (!scope)
                return;
            var session = scope.getSession && scope.getSession();
            if (session) {
                if (client && client.captureSession) {
                    client.captureSession(session);
                }
            }
        };
        /**
         * Internal helper function to call a method on the top client if it exists.
         *
         * @param method The method to call on the client.
         * @param args Arguments to pass to the client function.
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Hub.prototype._invokeClient = function (method) {
            var _a;
            var args = [];
            for (var _i = 1; _i < arguments.length; _i++) {
                args[_i - 1] = arguments[_i];
            }
            var _b = this.getStackTop(), scope = _b.scope, client = _b.client;
            if (client && client[method]) {
                // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-explicit-any
                (_a = client)[method].apply(_a, __spread(args, [scope]));
            }
        };
        /**
         * Calls global extension method and binding current instance to the function call
         */
        // @ts-ignore Function lacks ending return statement and return type does not include 'undefined'. ts(2366)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Hub.prototype._callExtensionMethod = function (method) {
            var args = [];
            for (var _i = 1; _i < arguments.length; _i++) {
                args[_i - 1] = arguments[_i];
            }
            var carrier = getMainCarrier();
            var sentry = carrier.__SENTRY__;
            if (sentry && sentry.extensions && typeof sentry.extensions[method] === 'function') {
                return sentry.extensions[method].apply(this, args);
            }
            logger.warn("Extension method " + method + " couldn't be found, doing nothing.");
        };
        return Hub;
    }());
    /**
     * Returns the global shim registry.
     *
     * FIXME: This function is problematic, because despite always returning a valid Carrier,
     * it has an optional `__SENTRY__` property, which then in turn requires us to always perform an unnecessary check
     * at the call-site. We always access the carrier through this function, so we can guarantee that `__SENTRY__` is there.
     **/
    function getMainCarrier() {
        var carrier = getGlobalObject();
        carrier.__SENTRY__ = carrier.__SENTRY__ || {
            extensions: {},
            hub: undefined,
        };
        return carrier;
    }
    /**
     * Replaces the current main hub with the passed one on the global object
     *
     * @returns The old replaced hub
     */
    function makeMain(hub) {
        var registry = getMainCarrier();
        var oldHub = getHubFromCarrier(registry);
        setHubOnCarrier(registry, hub);
        return oldHub;
    }
    /**
     * Returns the default hub instance.
     *
     * If a hub is already registered in the global carrier but this module
     * contains a more recent version, it replaces the registered version.
     * Otherwise, the currently registered hub will be returned.
     */
    function getCurrentHub() {
        // Get main carrier (global for every environment)
        var registry = getMainCarrier();
        // If there's no hub, or its an old API, assign a new one
        if (!hasHubOnCarrier(registry) || getHubFromCarrier(registry).isOlderThan(API_VERSION)) {
            setHubOnCarrier(registry, new Hub());
        }
        // Prefer domains over global if they are there (applicable only to Node environment)
        if (isNodeEnv()) {
            return getHubFromActiveDomain(registry);
        }
        // Return hub that lives on a global object
        return getHubFromCarrier(registry);
    }
    /**
     * Try to read the hub from an active domain, and fallback to the registry if one doesn't exist
     * @returns discovered hub
     */
    function getHubFromActiveDomain(registry) {
        var _a, _b, _c;
        try {
            var activeDomain = (_c = (_b = (_a = getMainCarrier().__SENTRY__) === null || _a === void 0 ? void 0 : _a.extensions) === null || _b === void 0 ? void 0 : _b.domain) === null || _c === void 0 ? void 0 : _c.active;
            // If there's no active domain, just return global hub
            if (!activeDomain) {
                return getHubFromCarrier(registry);
            }
            // If there's no hub on current domain, or it's an old API, assign a new one
            if (!hasHubOnCarrier(activeDomain) || getHubFromCarrier(activeDomain).isOlderThan(API_VERSION)) {
                var registryHubTopStack = getHubFromCarrier(registry).getStackTop();
                setHubOnCarrier(activeDomain, new Hub(registryHubTopStack.client, Scope.clone(registryHubTopStack.scope)));
            }
            // Return hub that lives on a domain
            return getHubFromCarrier(activeDomain);
        }
        catch (_Oo) {
            // Return hub that lives on a global object
            return getHubFromCarrier(registry);
        }
    }
    /**
     * This will tell whether a carrier has a hub on it or not
     * @param carrier object
     */
    function hasHubOnCarrier(carrier) {
        return !!(carrier && carrier.__SENTRY__ && carrier.__SENTRY__.hub);
    }
    /**
     * This will create a new {@link Hub} and add to the passed object on
     * __SENTRY__.hub.
     * @param carrier object
     * @hidden
     */
    function getHubFromCarrier(carrier) {
        if (carrier && carrier.__SENTRY__ && carrier.__SENTRY__.hub)
            return carrier.__SENTRY__.hub;
        carrier.__SENTRY__ = carrier.__SENTRY__ || {};
        carrier.__SENTRY__.hub = new Hub();
        return carrier.__SENTRY__.hub;
    }
    /**
     * This will set passed {@link Hub} on the passed object's __SENTRY__.hub attribute
     * @param carrier object
     * @param hub Hub
     * @returns A boolean indicating success or failure
     */
    function setHubOnCarrier(carrier, hub) {
        if (!carrier)
            return false;
        carrier.__SENTRY__ = carrier.__SENTRY__ || {};
        carrier.__SENTRY__.hub = hub;
        return true;
    }

    /**
     * This calls a function on the current hub.
     * @param method function to call on hub.
     * @param args to pass to function.
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function callOnHub(method) {
        var args = [];
        for (var _i = 1; _i < arguments.length; _i++) {
            args[_i - 1] = arguments[_i];
        }
        var hub = getCurrentHub();
        if (hub && hub[method]) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return hub[method].apply(hub, __spread(args));
        }
        throw new Error("No hub defined or " + method + " was not found on the hub, please open a bug report.");
    }
    /**
     * Captures an exception event and sends it to Sentry.
     *
     * @param exception An exception-like object.
     * @returns The generated eventId.
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
    function captureException(exception, captureContext) {
        var syntheticException;
        try {
            throw new Error('Sentry syntheticException');
        }
        catch (exception) {
            syntheticException = exception;
        }
        return callOnHub('captureException', exception, {
            captureContext: captureContext,
            originalException: exception,
            syntheticException: syntheticException,
        });
    }
    /**
     * Captures a message event and sends it to Sentry.
     *
     * @param message The message to send to Sentry.
     * @param level Define the level of the message.
     * @returns The generated eventId.
     */
    function captureMessage(message, captureContext) {
        var syntheticException;
        try {
            throw new Error(message);
        }
        catch (exception) {
            syntheticException = exception;
        }
        // This is necessary to provide explicit scopes upgrade, without changing the original
        // arity of the `captureMessage(message, level)` method.
        var level = typeof captureContext === 'string' ? captureContext : undefined;
        var context = typeof captureContext !== 'string' ? { captureContext: captureContext } : undefined;
        return callOnHub('captureMessage', message, level, __assign({ originalException: message, syntheticException: syntheticException }, context));
    }
    /**
     * Captures a manually created event and sends it to Sentry.
     *
     * @param event The event to send to Sentry.
     * @returns The generated eventId.
     */
    function captureEvent(event) {
        return callOnHub('captureEvent', event);
    }
    /**
     * Callback to set context information onto the scope.
     * @param callback Callback function that receives Scope.
     */
    function configureScope(callback) {
        callOnHub('configureScope', callback);
    }
    /**
     * Records a new breadcrumb which will be attached to future events.
     *
     * Breadcrumbs will be added to subsequent events to provide more context on
     * user's actions prior to an error or crash.
     *
     * @param breadcrumb The breadcrumb to record.
     */
    function addBreadcrumb(breadcrumb) {
        callOnHub('addBreadcrumb', breadcrumb);
    }
    /**
     * Sets context data with the given name.
     * @param name of the context
     * @param context Any kind of data. This data will be normalized.
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function setContext(name, context) {
        callOnHub('setContext', name, context);
    }
    /**
     * Set an object that will be merged sent as extra data with the event.
     * @param extras Extras object to merge into current context.
     */
    function setExtras(extras) {
        callOnHub('setExtras', extras);
    }
    /**
     * Set an object that will be merged sent as tags data with the event.
     * @param tags Tags context object to merge into current context.
     */
    function setTags(tags) {
        callOnHub('setTags', tags);
    }
    /**
     * Set key:value that will be sent as extra data with the event.
     * @param key String of extra
     * @param extra Any kind of data. This data will be normalized.
     */
    function setExtra(key, extra) {
        callOnHub('setExtra', key, extra);
    }
    /**
     * Set key:value that will be sent as tags data with the event.
     *
     * Can also be used to unset a tag, by passing `undefined`.
     *
     * @param key String key of tag
     * @param value Value of tag
     */
    function setTag(key, value) {
        callOnHub('setTag', key, value);
    }
    /**
     * Updates user context information for future events.
     *
     * @param user User context object to be set in the current context. Pass `null` to unset the user.
     */
    function setUser(user) {
        callOnHub('setUser', user);
    }
    /**
     * Creates a new scope with and executes the given operation within.
     * The scope is automatically removed once the operation
     * finishes or throws.
     *
     * This is essentially a convenience function for:
     *
     *     pushScope();
     *     callback();
     *     popScope();
     *
     * @param callback that will be enclosed into push/popScope.
     */
    function withScope(callback) {
        callOnHub('withScope', callback);
    }
    /**
     * Starts a new `Transaction` and returns it. This is the entry point to manual tracing instrumentation.
     *
     * A tree structure can be built by adding child spans to the transaction, and child spans to other spans. To start a
     * new child span within the transaction or any span, call the respective `.startChild()` method.
     *
     * Every child span must be finished before the transaction is finished, otherwise the unfinished spans are discarded.
     *
     * The transaction must be finished with a call to its `.finish()` method, at which point the transaction with all its
     * finished child spans will be sent to Sentry.
     *
     * @param context Properties of the new `Transaction`.
     * @param customSamplingContext Information given to the transaction sampling function (along with context-dependent
     * default values). See {@link Options.tracesSampler}.
     *
     * @returns The transaction which was just started
     */
    function startTransaction(context, customSamplingContext) {
        return callOnHub('startTransaction', __assign({}, context), customSamplingContext);
    }

    var SENTRY_API_VERSION = '7';
    /**
     * Helper class to provide urls, headers and metadata that can be used to form
     * different types of requests to Sentry endpoints.
     * Supports both envelopes and regular event requests.
     **/
    var API = /** @class */ (function () {
        /** Create a new instance of API */
        function API(dsn, metadata, tunnel) {
            if (metadata === void 0) { metadata = {}; }
            this.dsn = dsn;
            this._dsnObject = new Dsn(dsn);
            this.metadata = metadata;
            this._tunnel = tunnel;
        }
        /** Returns the Dsn object. */
        API.prototype.getDsn = function () {
            return this._dsnObject;
        };
        /** Does this transport force envelopes? */
        API.prototype.forceEnvelope = function () {
            return !!this._tunnel;
        };
        /** Returns the prefix to construct Sentry ingestion API endpoints. */
        API.prototype.getBaseApiEndpoint = function () {
            var dsn = this.getDsn();
            var protocol = dsn.protocol ? dsn.protocol + ":" : '';
            var port = dsn.port ? ":" + dsn.port : '';
            return protocol + "//" + dsn.host + port + (dsn.path ? "/" + dsn.path : '') + "/api/";
        };
        /** Returns the store endpoint URL. */
        API.prototype.getStoreEndpoint = function () {
            return this._getIngestEndpoint('store');
        };
        /**
         * Returns the store endpoint URL with auth in the query string.
         *
         * Sending auth as part of the query string and not as custom HTTP headers avoids CORS preflight requests.
         */
        API.prototype.getStoreEndpointWithUrlEncodedAuth = function () {
            return this.getStoreEndpoint() + "?" + this._encodedAuth();
        };
        /**
         * Returns the envelope endpoint URL with auth in the query string.
         *
         * Sending auth as part of the query string and not as custom HTTP headers avoids CORS preflight requests.
         */
        API.prototype.getEnvelopeEndpointWithUrlEncodedAuth = function () {
            if (this.forceEnvelope()) {
                return this._tunnel;
            }
            return this._getEnvelopeEndpoint() + "?" + this._encodedAuth();
        };
        /** Returns only the path component for the store endpoint. */
        API.prototype.getStoreEndpointPath = function () {
            var dsn = this.getDsn();
            return (dsn.path ? "/" + dsn.path : '') + "/api/" + dsn.projectId + "/store/";
        };
        /**
         * Returns an object that can be used in request headers.
         * This is needed for node and the old /store endpoint in sentry
         */
        API.prototype.getRequestHeaders = function (clientName, clientVersion) {
            // CHANGE THIS to use metadata but keep clientName and clientVersion compatible
            var dsn = this.getDsn();
            var header = ["Sentry sentry_version=" + SENTRY_API_VERSION];
            header.push("sentry_client=" + clientName + "/" + clientVersion);
            header.push("sentry_key=" + dsn.publicKey);
            if (dsn.pass) {
                header.push("sentry_secret=" + dsn.pass);
            }
            return {
                'Content-Type': 'application/json',
                'X-Sentry-Auth': header.join(', '),
            };
        };
        /** Returns the url to the report dialog endpoint. */
        API.prototype.getReportDialogEndpoint = function (dialogOptions) {
            if (dialogOptions === void 0) { dialogOptions = {}; }
            var dsn = this.getDsn();
            var endpoint = this.getBaseApiEndpoint() + "embed/error-page/";
            var encodedOptions = [];
            encodedOptions.push("dsn=" + dsn.toString());
            for (var key in dialogOptions) {
                if (key === 'dsn') {
                    continue;
                }
                if (key === 'user') {
                    if (!dialogOptions.user) {
                        continue;
                    }
                    if (dialogOptions.user.name) {
                        encodedOptions.push("name=" + encodeURIComponent(dialogOptions.user.name));
                    }
                    if (dialogOptions.user.email) {
                        encodedOptions.push("email=" + encodeURIComponent(dialogOptions.user.email));
                    }
                }
                else {
                    encodedOptions.push(encodeURIComponent(key) + "=" + encodeURIComponent(dialogOptions[key]));
                }
            }
            if (encodedOptions.length) {
                return endpoint + "?" + encodedOptions.join('&');
            }
            return endpoint;
        };
        /** Returns the envelope endpoint URL. */
        API.prototype._getEnvelopeEndpoint = function () {
            return this._getIngestEndpoint('envelope');
        };
        /** Returns the ingest API endpoint for target. */
        API.prototype._getIngestEndpoint = function (target) {
            if (this._tunnel) {
                return this._tunnel;
            }
            var base = this.getBaseApiEndpoint();
            var dsn = this.getDsn();
            return "" + base + dsn.projectId + "/" + target + "/";
        };
        /** Returns a URL-encoded string with auth config suitable for a query string. */
        API.prototype._encodedAuth = function () {
            var dsn = this.getDsn();
            var auth = {
                // We send only the minimum set of required information. See
                // https://github.com/getsentry/sentry-javascript/issues/2572.
                sentry_key: dsn.publicKey,
                sentry_version: SENTRY_API_VERSION,
            };
            return urlEncode(auth);
        };
        return API;
    }());

    var installedIntegrations = [];
    /**
     * @private
     */
    function filterDuplicates(integrations) {
        return integrations.reduce(function (acc, integrations) {
            if (acc.every(function (accIntegration) { return integrations.name !== accIntegration.name; })) {
                acc.push(integrations);
            }
            return acc;
        }, []);
    }
    /** Gets integration to install */
    function getIntegrationsToSetup(options) {
        var defaultIntegrations = (options.defaultIntegrations && __spread(options.defaultIntegrations)) || [];
        var userIntegrations = options.integrations;
        var integrations = __spread(filterDuplicates(defaultIntegrations));
        if (Array.isArray(userIntegrations)) {
            // Filter out integrations that are also included in user options
            integrations = __spread(integrations.filter(function (integrations) {
                return userIntegrations.every(function (userIntegration) { return userIntegration.name !== integrations.name; });
            }), filterDuplicates(userIntegrations));
        }
        else if (typeof userIntegrations === 'function') {
            integrations = userIntegrations(integrations);
            integrations = Array.isArray(integrations) ? integrations : [integrations];
        }
        // Make sure that if present, `Debug` integration will always run last
        var integrationsNames = integrations.map(function (i) { return i.name; });
        var alwaysLastToRun = 'Debug';
        if (integrationsNames.indexOf(alwaysLastToRun) !== -1) {
            integrations.push.apply(integrations, __spread(integrations.splice(integrationsNames.indexOf(alwaysLastToRun), 1)));
        }
        return integrations;
    }
    /** Setup given integration */
    function setupIntegration(integration) {
        if (installedIntegrations.indexOf(integration.name) !== -1) {
            return;
        }
        integration.setupOnce(addGlobalEventProcessor, getCurrentHub);
        installedIntegrations.push(integration.name);
        logger.log("Integration installed: " + integration.name);
    }
    /**
     * Given a list of integration instances this installs them all. When `withDefaults` is set to `true` then all default
     * integrations are added unless they were already provided before.
     * @param integrations array of integration instances
     * @param withDefault should enable default integrations
     */
    function setupIntegrations(options) {
        var integrations = {};
        getIntegrationsToSetup(options).forEach(function (integration) {
            integrations[integration.name] = integration;
            setupIntegration(integration);
        });
        // set the `initialized` flag so we don't run through the process again unecessarily; use `Object.defineProperty`
        // because by default it creates a property which is nonenumerable, which we want since `initialized` shouldn't be
        // considered a member of the index the way the actual integrations are
        Object.defineProperty(integrations, 'initialized', { value: true });
        return integrations;
    }

    /**
     * Base implementation for all JavaScript SDK clients.
     *
     * Call the constructor with the corresponding backend constructor and options
     * specific to the client subclass. To access these options later, use
     * {@link Client.getOptions}. Also, the Backend instance is available via
     * {@link Client.getBackend}.
     *
     * If a Dsn is specified in the options, it will be parsed and stored. Use
     * {@link Client.getDsn} to retrieve the Dsn at any moment. In case the Dsn is
     * invalid, the constructor will throw a {@link SentryException}. Note that
     * without a valid Dsn, the SDK will not send any events to Sentry.
     *
     * Before sending an event via the backend, it is passed through
     * {@link BaseClient._prepareEvent} to add SDK information and scope data
     * (breadcrumbs and context). To add more custom information, override this
     * method and extend the resulting prepared event.
     *
     * To issue automatically created events (e.g. via instrumentation), use
     * {@link Client.captureEvent}. It will prepare the event and pass it through
     * the callback lifecycle. To issue auto-breadcrumbs, use
     * {@link Client.addBreadcrumb}.
     *
     * @example
     * class NodeClient extends BaseClient<NodeBackend, NodeOptions> {
     *   public constructor(options: NodeOptions) {
     *     super(NodeBackend, options);
     *   }
     *
     *   // ...
     * }
     */
    var BaseClient = /** @class */ (function () {
        /**
         * Initializes this client instance.
         *
         * @param backendClass A constructor function to create the backend.
         * @param options Options for the client.
         */
        function BaseClient(backendClass, options) {
            /** Array of used integrations. */
            this._integrations = {};
            /** Number of calls being processed */
            this._numProcessing = 0;
            this._backend = new backendClass(options);
            this._options = options;
            if (options.dsn) {
                this._dsn = new Dsn(options.dsn);
            }
        }
        /**
         * @inheritDoc
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
        BaseClient.prototype.captureException = function (exception, hint, scope) {
            var _this = this;
            var eventId = hint && hint.event_id;
            this._process(this._getBackend()
                .eventFromException(exception, hint)
                .then(function (event) { return _this._captureEvent(event, hint, scope); })
                .then(function (result) {
                eventId = result;
            }));
            return eventId;
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.captureMessage = function (message, level, hint, scope) {
            var _this = this;
            var eventId = hint && hint.event_id;
            var promisedEvent = isPrimitive(message)
                ? this._getBackend().eventFromMessage(String(message), level, hint)
                : this._getBackend().eventFromException(message, hint);
            this._process(promisedEvent
                .then(function (event) { return _this._captureEvent(event, hint, scope); })
                .then(function (result) {
                eventId = result;
            }));
            return eventId;
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.captureEvent = function (event, hint, scope) {
            var eventId = hint && hint.event_id;
            this._process(this._captureEvent(event, hint, scope).then(function (result) {
                eventId = result;
            }));
            return eventId;
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.captureSession = function (session) {
            if (!this._isEnabled()) {
                logger.warn('SDK not enabled, will not capture session.');
                return;
            }
            if (!(typeof session.release === 'string')) {
                logger.warn('Discarded session because of missing or non-string release');
            }
            else {
                this._sendSession(session);
                // After sending, we set init false to indicate it's not the first occurrence
                session.update({ init: false });
            }
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.getDsn = function () {
            return this._dsn;
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.getOptions = function () {
            return this._options;
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.flush = function (timeout) {
            var _this = this;
            return this._isClientDoneProcessing(timeout).then(function (clientFinished) {
                return _this._getBackend()
                    .getTransport()
                    .close(timeout)
                    .then(function (transportFlushed) { return clientFinished && transportFlushed; });
            });
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.close = function (timeout) {
            var _this = this;
            return this.flush(timeout).then(function (result) {
                _this.getOptions().enabled = false;
                return result;
            });
        };
        /**
         * Sets up the integrations
         */
        BaseClient.prototype.setupIntegrations = function () {
            if (this._isEnabled() && !this._integrations.initialized) {
                this._integrations = setupIntegrations(this._options);
            }
        };
        /**
         * @inheritDoc
         */
        BaseClient.prototype.getIntegration = function (integration) {
            try {
                return this._integrations[integration.id] || null;
            }
            catch (_oO) {
                logger.warn("Cannot retrieve integration " + integration.id + " from the current Client");
                return null;
            }
        };
        /** Updates existing session based on the provided event */
        BaseClient.prototype._updateSessionFromEvent = function (session, event) {
            var e_1, _a;
            var crashed = false;
            var errored = false;
            var exceptions = event.exception && event.exception.values;
            if (exceptions) {
                errored = true;
                try {
                    for (var exceptions_1 = __values(exceptions), exceptions_1_1 = exceptions_1.next(); !exceptions_1_1.done; exceptions_1_1 = exceptions_1.next()) {
                        var ex = exceptions_1_1.value;
                        var mechanism = ex.mechanism;
                        if (mechanism && mechanism.handled === false) {
                            crashed = true;
                            break;
                        }
                    }
                }
                catch (e_1_1) { e_1 = { error: e_1_1 }; }
                finally {
                    try {
                        if (exceptions_1_1 && !exceptions_1_1.done && (_a = exceptions_1.return)) _a.call(exceptions_1);
                    }
                    finally { if (e_1) throw e_1.error; }
                }
            }
            // A session is updated and that session update is sent in only one of the two following scenarios:
            // 1. Session with non terminal status and 0 errors + an error occurred -> Will set error count to 1 and send update
            // 2. Session with non terminal status and 1 error + a crash occurred -> Will set status crashed and send update
            var sessionNonTerminal = session.status === SessionStatus.Ok;
            var shouldUpdateAndSend = (sessionNonTerminal && session.errors === 0) || (sessionNonTerminal && crashed);
            if (shouldUpdateAndSend) {
                session.update(__assign(__assign({}, (crashed && { status: SessionStatus.Crashed })), { errors: session.errors || Number(errored || crashed) }));
                this.captureSession(session);
            }
        };
        /** Deliver captured session to Sentry */
        BaseClient.prototype._sendSession = function (session) {
            this._getBackend().sendSession(session);
        };
        /**
         * Determine if the client is finished processing. Returns a promise because it will wait `timeout` ms before saying
         * "no" (resolving to `false`) in order to give the client a chance to potentially finish first.
         *
         * @param timeout The time, in ms, after which to resolve to `false` if the client is still busy. Passing `0` (or not
         * passing anything) will make the promise wait as long as it takes for processing to finish before resolving to
         * `true`.
         * @returns A promise which will resolve to `true` if processing is already done or finishes before the timeout, and
         * `false` otherwise
         */
        BaseClient.prototype._isClientDoneProcessing = function (timeout) {
            var _this = this;
            return new SyncPromise(function (resolve) {
                var ticked = 0;
                var tick = 1;
                var interval = setInterval(function () {
                    if (_this._numProcessing == 0) {
                        clearInterval(interval);
                        resolve(true);
                    }
                    else {
                        ticked += tick;
                        if (timeout && ticked >= timeout) {
                            clearInterval(interval);
                            resolve(false);
                        }
                    }
                }, tick);
            });
        };
        /** Returns the current backend. */
        BaseClient.prototype._getBackend = function () {
            return this._backend;
        };
        /** Determines whether this SDK is enabled and a valid Dsn is present. */
        BaseClient.prototype._isEnabled = function () {
            return this.getOptions().enabled !== false && this._dsn !== undefined;
        };
        /**
         * Adds common information to events.
         *
         * The information includes release and environment from `options`,
         * breadcrumbs and context (extra, tags and user) from the scope.
         *
         * Information that is already present in the event is never overwritten. For
         * nested objects, such as the context, keys are merged.
         *
         * @param event The original event.
         * @param hint May contain additional information about the original exception.
         * @param scope A scope containing event metadata.
         * @returns A new event with more information.
         */
        BaseClient.prototype._prepareEvent = function (event, scope, hint) {
            var _this = this;
            var _a = this.getOptions().normalizeDepth, normalizeDepth = _a === void 0 ? 3 : _a;
            var prepared = __assign(__assign({}, event), { event_id: event.event_id || (hint && hint.event_id ? hint.event_id : uuid4()), timestamp: event.timestamp || dateTimestampInSeconds() });
            this._applyClientOptions(prepared);
            this._applyIntegrationsMetadata(prepared);
            // If we have scope given to us, use it as the base for further modifications.
            // This allows us to prevent unnecessary copying of data if `captureContext` is not provided.
            var finalScope = scope;
            if (hint && hint.captureContext) {
                finalScope = Scope.clone(finalScope).update(hint.captureContext);
            }
            // We prepare the result here with a resolved Event.
            var result = SyncPromise.resolve(prepared);
            // This should be the last thing called, since we want that
            // {@link Hub.addEventProcessor} gets the finished prepared event.
            if (finalScope) {
                // In case we have a hub we reassign it.
                result = finalScope.applyToEvent(prepared, hint);
            }
            return result.then(function (evt) {
                if (typeof normalizeDepth === 'number' && normalizeDepth > 0) {
                    return _this._normalizeEvent(evt, normalizeDepth);
                }
                return evt;
            });
        };
        /**
         * Applies `normalize` function on necessary `Event` attributes to make them safe for serialization.
         * Normalized keys:
         * - `breadcrumbs.data`
         * - `user`
         * - `contexts`
         * - `extra`
         * @param event Event
         * @returns Normalized event
         */
        BaseClient.prototype._normalizeEvent = function (event, depth) {
            if (!event) {
                return null;
            }
            var normalized = __assign(__assign(__assign(__assign(__assign({}, event), (event.breadcrumbs && {
                breadcrumbs: event.breadcrumbs.map(function (b) { return (__assign(__assign({}, b), (b.data && {
                    data: normalize(b.data, depth),
                }))); }),
            })), (event.user && {
                user: normalize(event.user, depth),
            })), (event.contexts && {
                contexts: normalize(event.contexts, depth),
            })), (event.extra && {
                extra: normalize(event.extra, depth),
            }));
            // event.contexts.trace stores information about a Transaction. Similarly,
            // event.spans[] stores information about child Spans. Given that a
            // Transaction is conceptually a Span, normalization should apply to both
            // Transactions and Spans consistently.
            // For now the decision is to skip normalization of Transactions and Spans,
            // so this block overwrites the normalized event to add back the original
            // Transaction information prior to normalization.
            if (event.contexts && event.contexts.trace) {
                // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                normalized.contexts.trace = event.contexts.trace;
            }
            var _a = this.getOptions()._experiments, _experiments = _a === void 0 ? {} : _a;
            if (_experiments.ensureNoCircularStructures) {
                return normalize(normalized);
            }
            return normalized;
        };
        /**
         *  Enhances event using the client configuration.
         *  It takes care of all "static" values like environment, release and `dist`,
         *  as well as truncating overly long values.
         * @param event event instance to be enhanced
         */
        BaseClient.prototype._applyClientOptions = function (event) {
            var options = this.getOptions();
            var environment = options.environment, release = options.release, dist = options.dist, _a = options.maxValueLength, maxValueLength = _a === void 0 ? 250 : _a;
            if (!('environment' in event)) {
                event.environment = 'environment' in options ? environment : 'production';
            }
            if (event.release === undefined && release !== undefined) {
                event.release = release;
            }
            if (event.dist === undefined && dist !== undefined) {
                event.dist = dist;
            }
            if (event.message) {
                event.message = truncate(event.message, maxValueLength);
            }
            var exception = event.exception && event.exception.values && event.exception.values[0];
            if (exception && exception.value) {
                exception.value = truncate(exception.value, maxValueLength);
            }
            var request = event.request;
            if (request && request.url) {
                request.url = truncate(request.url, maxValueLength);
            }
        };
        /**
         * This function adds all used integrations to the SDK info in the event.
         * @param event The event that will be filled with all integrations.
         */
        BaseClient.prototype._applyIntegrationsMetadata = function (event) {
            var integrationsArray = Object.keys(this._integrations);
            if (integrationsArray.length > 0) {
                event.sdk = event.sdk || {};
                event.sdk.integrations = __spread((event.sdk.integrations || []), integrationsArray);
            }
        };
        /**
         * Tells the backend to send this event
         * @param event The Sentry event to send
         */
        BaseClient.prototype._sendEvent = function (event) {
            this._getBackend().sendEvent(event);
        };
        /**
         * Processes the event and logs an error in case of rejection
         * @param event
         * @param hint
         * @param scope
         */
        BaseClient.prototype._captureEvent = function (event, hint, scope) {
            return this._processEvent(event, hint, scope).then(function (finalEvent) {
                return finalEvent.event_id;
            }, function (reason) {
                logger.error(reason);
                return undefined;
            });
        };
        /**
         * Processes an event (either error or message) and sends it to Sentry.
         *
         * This also adds breadcrumbs and context information to the event. However,
         * platform specific meta data (such as the User's IP address) must be added
         * by the SDK implementor.
         *
         *
         * @param event The event to send to Sentry.
         * @param hint May contain additional information about the original exception.
         * @param scope A scope containing event metadata.
         * @returns A SyncPromise that resolves with the event or rejects in case event was/will not be send.
         */
        BaseClient.prototype._processEvent = function (event, hint, scope) {
            var _this = this;
            // eslint-disable-next-line @typescript-eslint/unbound-method
            var _a = this.getOptions(), beforeSend = _a.beforeSend, sampleRate = _a.sampleRate;
            if (!this._isEnabled()) {
                return SyncPromise.reject(new SentryError('SDK not enabled, will not capture event.'));
            }
            var isTransaction = event.type === 'transaction';
            // 1.0 === 100% events are sent
            // 0.0 === 0% events are sent
            // Sampling for transaction happens somewhere else
            if (!isTransaction && typeof sampleRate === 'number' && Math.random() > sampleRate) {
                return SyncPromise.reject(new SentryError("Discarding event because it's not included in the random sample (sampling rate = " + sampleRate + ")"));
            }
            return this._prepareEvent(event, scope, hint)
                .then(function (prepared) {
                if (prepared === null) {
                    throw new SentryError('An event processor returned null, will not send event.');
                }
                var isInternalException = hint && hint.data && hint.data.__sentry__ === true;
                if (isInternalException || isTransaction || !beforeSend) {
                    return prepared;
                }
                var beforeSendResult = beforeSend(prepared, hint);
                return _this._ensureBeforeSendRv(beforeSendResult);
            })
                .then(function (processedEvent) {
                if (processedEvent === null) {
                    throw new SentryError('`beforeSend` returned `null`, will not send event.');
                }
                var session = scope && scope.getSession && scope.getSession();
                if (!isTransaction && session) {
                    _this._updateSessionFromEvent(session, processedEvent);
                }
                _this._sendEvent(processedEvent);
                return processedEvent;
            })
                .then(null, function (reason) {
                if (reason instanceof SentryError) {
                    throw reason;
                }
                _this.captureException(reason, {
                    data: {
                        __sentry__: true,
                    },
                    originalException: reason,
                });
                throw new SentryError("Event processing pipeline threw an error, original event will not be sent. Details have been sent as a new event.\nReason: " + reason);
            });
        };
        /**
         * Occupies the client with processing and event
         */
        BaseClient.prototype._process = function (promise) {
            var _this = this;
            this._numProcessing += 1;
            void promise.then(function (value) {
                _this._numProcessing -= 1;
                return value;
            }, function (reason) {
                _this._numProcessing -= 1;
                return reason;
            });
        };
        /**
         * Verifies that return value of configured `beforeSend` is of expected type.
         */
        BaseClient.prototype._ensureBeforeSendRv = function (rv) {
            var nullErr = '`beforeSend` method has to return `null` or a valid event.';
            if (isThenable(rv)) {
                return rv.then(function (event) {
                    if (!(isPlainObject(event) || event === null)) {
                        throw new SentryError(nullErr);
                    }
                    return event;
                }, function (e) {
                    throw new SentryError("beforeSend rejected with " + e);
                });
            }
            else if (!(isPlainObject(rv) || rv === null)) {
                throw new SentryError(nullErr);
            }
            return rv;
        };
        return BaseClient;
    }());

    /** Noop transport */
    var NoopTransport = /** @class */ (function () {
        function NoopTransport() {
        }
        /**
         * @inheritDoc
         */
        NoopTransport.prototype.sendEvent = function (_) {
            return SyncPromise.resolve({
                reason: "NoopTransport: Event has been skipped because no Dsn is configured.",
                status: exports.Status.Skipped,
            });
        };
        /**
         * @inheritDoc
         */
        NoopTransport.prototype.close = function (_) {
            return SyncPromise.resolve(true);
        };
        return NoopTransport;
    }());

    /**
     * This is the base implemention of a Backend.
     * @hidden
     */
    var BaseBackend = /** @class */ (function () {
        /** Creates a new backend instance. */
        function BaseBackend(options) {
            this._options = options;
            if (!this._options.dsn) {
                logger.warn('No DSN provided, backend will not do anything.');
            }
            this._transport = this._setupTransport();
        }
        /**
         * @inheritDoc
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
        BaseBackend.prototype.eventFromException = function (_exception, _hint) {
            throw new SentryError('Backend has to implement `eventFromException` method');
        };
        /**
         * @inheritDoc
         */
        BaseBackend.prototype.eventFromMessage = function (_message, _level, _hint) {
            throw new SentryError('Backend has to implement `eventFromMessage` method');
        };
        /**
         * @inheritDoc
         */
        BaseBackend.prototype.sendEvent = function (event) {
            void this._transport.sendEvent(event).then(null, function (reason) {
                logger.error("Error while sending event: " + reason);
            });
        };
        /**
         * @inheritDoc
         */
        BaseBackend.prototype.sendSession = function (session) {
            if (!this._transport.sendSession) {
                logger.warn("Dropping session because custom transport doesn't implement sendSession");
                return;
            }
            void this._transport.sendSession(session).then(null, function (reason) {
                logger.error("Error while sending session: " + reason);
            });
        };
        /**
         * @inheritDoc
         */
        BaseBackend.prototype.getTransport = function () {
            return this._transport;
        };
        /**
         * Sets up the transport so it can be used later to send requests.
         */
        BaseBackend.prototype._setupTransport = function () {
            return new NoopTransport();
        };
        return BaseBackend;
    }());

    /** Extract sdk info from from the API metadata */
    function getSdkMetadataForEnvelopeHeader(api) {
        if (!api.metadata || !api.metadata.sdk) {
            return;
        }
        var _a = api.metadata.sdk, name = _a.name, version = _a.version;
        return { name: name, version: version };
    }
    /**
     * Apply SdkInfo (name, version, packages, integrations) to the corresponding event key.
     * Merge with existing data if any.
     **/
    function enhanceEventWithSdkInfo(event, sdkInfo) {
        if (!sdkInfo) {
            return event;
        }
        event.sdk = event.sdk || {};
        event.sdk.name = event.sdk.name || sdkInfo.name;
        event.sdk.version = event.sdk.version || sdkInfo.version;
        event.sdk.integrations = __spread((event.sdk.integrations || []), (sdkInfo.integrations || []));
        event.sdk.packages = __spread((event.sdk.packages || []), (sdkInfo.packages || []));
        return event;
    }
    /** Creates a SentryRequest from a Session. */
    function sessionToSentryRequest(session, api) {
        var sdkInfo = getSdkMetadataForEnvelopeHeader(api);
        var envelopeHeaders = JSON.stringify(__assign(__assign({ sent_at: new Date().toISOString() }, (sdkInfo && { sdk: sdkInfo })), (api.forceEnvelope() && { dsn: api.getDsn().toString() })));
        // I know this is hacky but we don't want to add `session` to request type since it's never rate limited
        var type = 'aggregates' in session ? 'sessions' : 'session';
        var itemHeaders = JSON.stringify({
            type: type,
        });
        return {
            body: envelopeHeaders + "\n" + itemHeaders + "\n" + JSON.stringify(session),
            type: type,
            url: api.getEnvelopeEndpointWithUrlEncodedAuth(),
        };
    }
    /** Creates a SentryRequest from an event. */
    function eventToSentryRequest(event, api) {
        var sdkInfo = getSdkMetadataForEnvelopeHeader(api);
        var eventType = event.type || 'event';
        var useEnvelope = eventType === 'transaction' || api.forceEnvelope();
        var _a = event.debug_meta || {}, transactionSampling = _a.transactionSampling, metadata = __rest(_a, ["transactionSampling"]);
        var _b = transactionSampling || {}, samplingMethod = _b.method, sampleRate = _b.rate;
        if (Object.keys(metadata).length === 0) {
            delete event.debug_meta;
        }
        else {
            event.debug_meta = metadata;
        }
        var req = {
            body: JSON.stringify(sdkInfo ? enhanceEventWithSdkInfo(event, api.metadata.sdk) : event),
            type: eventType,
            url: useEnvelope ? api.getEnvelopeEndpointWithUrlEncodedAuth() : api.getStoreEndpointWithUrlEncodedAuth(),
        };
        // https://develop.sentry.dev/sdk/envelopes/
        // Since we don't need to manipulate envelopes nor store them, there is no
        // exported concept of an Envelope with operations including serialization and
        // deserialization. Instead, we only implement a minimal subset of the spec to
        // serialize events inline here.
        if (useEnvelope) {
            var envelopeHeaders = JSON.stringify(__assign(__assign({ event_id: event.event_id, sent_at: new Date().toISOString() }, (sdkInfo && { sdk: sdkInfo })), (api.forceEnvelope() && { dsn: api.getDsn().toString() })));
            var itemHeaders = JSON.stringify({
                type: eventType,
                // TODO: Right now, sampleRate may or may not be defined (it won't be in the cases of inheritance and
                // explicitly-set sampling decisions). Are we good with that?
                sample_rates: [{ id: samplingMethod, rate: sampleRate }],
            });
            // The trailing newline is optional. We intentionally don't send it to avoid
            // sending unnecessary bytes.
            //
            // const envelope = `${envelopeHeaders}\n${itemHeaders}\n${req.body}\n`;
            var envelope = envelopeHeaders + "\n" + itemHeaders + "\n" + req.body;
            req.body = envelope;
        }
        return req;
    }

    /**
     * Internal function to create a new SDK client instance. The client is
     * installed and then bound to the current scope.
     *
     * @param clientClass The client class to instantiate.
     * @param options Options to pass to the client.
     */
    function initAndBind(clientClass, options) {
        var _a;
        if (options.debug === true) {
            logger.enable();
        }
        var hub = getCurrentHub();
        (_a = hub.getScope()) === null || _a === void 0 ? void 0 : _a.update(options.initialScope);
        var client = new clientClass(options);
        hub.bindClient(client);
    }

    var SDK_VERSION = '6.11.0';

    var originalFunctionToString;
    /** Patch toString calls to return proper name for wrapped functions */
    var FunctionToString = /** @class */ (function () {
        function FunctionToString() {
            /**
             * @inheritDoc
             */
            this.name = FunctionToString.id;
        }
        /**
         * @inheritDoc
         */
        FunctionToString.prototype.setupOnce = function () {
            // eslint-disable-next-line @typescript-eslint/unbound-method
            originalFunctionToString = Function.prototype.toString;
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            Function.prototype.toString = function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                var context = this.__sentry_original__ || this;
                return originalFunctionToString.apply(context, args);
            };
        };
        /**
         * @inheritDoc
         */
        FunctionToString.id = 'FunctionToString';
        return FunctionToString;
    }());

    // "Script error." is hard coded into browsers for errors that it can't read.
    // this is the result of a script being pulled in from an external domain and CORS.
    var DEFAULT_IGNORE_ERRORS = [/^Script error\.?$/, /^Javascript error: Script error\.? on line 0$/];
    /** Inbound filters configurable by the user */
    var InboundFilters = /** @class */ (function () {
        function InboundFilters(_options) {
            if (_options === void 0) { _options = {}; }
            this._options = _options;
            /**
             * @inheritDoc
             */
            this.name = InboundFilters.id;
        }
        /**
         * @inheritDoc
         */
        InboundFilters.prototype.setupOnce = function () {
            addGlobalEventProcessor(function (event) {
                var hub = getCurrentHub();
                if (!hub) {
                    return event;
                }
                var self = hub.getIntegration(InboundFilters);
                if (self) {
                    var client = hub.getClient();
                    var clientOptions = client ? client.getOptions() : {};
                    // This checks prevents most of the occurrences of the bug linked below:
                    // https://github.com/getsentry/sentry-javascript/issues/2622
                    // The bug is caused by multiple SDK instances, where one is minified and one is using non-mangled code.
                    // Unfortunatelly we cannot fix it reliably (thus reserved property in rollup's terser config),
                    // as we cannot force people using multiple instances in their apps to sync SDK versions.
                    var options = typeof self._mergeOptions === 'function' ? self._mergeOptions(clientOptions) : {};
                    if (typeof self._shouldDropEvent !== 'function') {
                        return event;
                    }
                    return self._shouldDropEvent(event, options) ? null : event;
                }
                return event;
            });
        };
        /** JSDoc */
        InboundFilters.prototype._shouldDropEvent = function (event, options) {
            if (this._isSentryError(event, options)) {
                logger.warn("Event dropped due to being internal Sentry Error.\nEvent: " + getEventDescription(event));
                return true;
            }
            if (this._isIgnoredError(event, options)) {
                logger.warn("Event dropped due to being matched by `ignoreErrors` option.\nEvent: " + getEventDescription(event));
                return true;
            }
            if (this._isDeniedUrl(event, options)) {
                logger.warn("Event dropped due to being matched by `denyUrls` option.\nEvent: " + getEventDescription(event) + ".\nUrl: " + this._getEventFilterUrl(event));
                return true;
            }
            if (!this._isAllowedUrl(event, options)) {
                logger.warn("Event dropped due to not being matched by `allowUrls` option.\nEvent: " + getEventDescription(event) + ".\nUrl: " + this._getEventFilterUrl(event));
                return true;
            }
            return false;
        };
        /** JSDoc */
        InboundFilters.prototype._isSentryError = function (event, options) {
            if (!options.ignoreInternal) {
                return false;
            }
            try {
                return ((event &&
                    event.exception &&
                    event.exception.values &&
                    event.exception.values[0] &&
                    event.exception.values[0].type === 'SentryError') ||
                    false);
            }
            catch (_oO) {
                return false;
            }
        };
        /** JSDoc */
        InboundFilters.prototype._isIgnoredError = function (event, options) {
            if (!options.ignoreErrors || !options.ignoreErrors.length) {
                return false;
            }
            return this._getPossibleEventMessages(event).some(function (message) {
                // Not sure why TypeScript complains here...
                return options.ignoreErrors.some(function (pattern) { return isMatchingPattern(message, pattern); });
            });
        };
        /** JSDoc */
        InboundFilters.prototype._isDeniedUrl = function (event, options) {
            // TODO: Use Glob instead?
            if (!options.denyUrls || !options.denyUrls.length) {
                return false;
            }
            var url = this._getEventFilterUrl(event);
            return !url ? false : options.denyUrls.some(function (pattern) { return isMatchingPattern(url, pattern); });
        };
        /** JSDoc */
        InboundFilters.prototype._isAllowedUrl = function (event, options) {
            // TODO: Use Glob instead?
            if (!options.allowUrls || !options.allowUrls.length) {
                return true;
            }
            var url = this._getEventFilterUrl(event);
            return !url ? true : options.allowUrls.some(function (pattern) { return isMatchingPattern(url, pattern); });
        };
        /** JSDoc */
        InboundFilters.prototype._mergeOptions = function (clientOptions) {
            if (clientOptions === void 0) { clientOptions = {}; }
            return {
                allowUrls: __spread((this._options.whitelistUrls || []), (this._options.allowUrls || []), (clientOptions.whitelistUrls || []), (clientOptions.allowUrls || [])),
                denyUrls: __spread((this._options.blacklistUrls || []), (this._options.denyUrls || []), (clientOptions.blacklistUrls || []), (clientOptions.denyUrls || [])),
                ignoreErrors: __spread((this._options.ignoreErrors || []), (clientOptions.ignoreErrors || []), DEFAULT_IGNORE_ERRORS),
                ignoreInternal: typeof this._options.ignoreInternal !== 'undefined' ? this._options.ignoreInternal : true,
            };
        };
        /** JSDoc */
        InboundFilters.prototype._getPossibleEventMessages = function (event) {
            if (event.message) {
                return [event.message];
            }
            if (event.exception) {
                try {
                    var _a = (event.exception.values && event.exception.values[0]) || {}, _b = _a.type, type = _b === void 0 ? '' : _b, _c = _a.value, value = _c === void 0 ? '' : _c;
                    return ["" + value, type + ": " + value];
                }
                catch (oO) {
                    logger.error("Cannot extract message for event " + getEventDescription(event));
                    return [];
                }
            }
            return [];
        };
        /** JSDoc */
        InboundFilters.prototype._getLastValidUrl = function (frames) {
            if (frames === void 0) { frames = []; }
            var _a;
            for (var i = frames.length - 1; i >= 0; i--) {
                var frame = frames[i];
                if (((_a = frame) === null || _a === void 0 ? void 0 : _a.filename) !== '<anonymous>') {
                    return frame.filename || null;
                }
            }
            return null;
        };
        /** JSDoc */
        InboundFilters.prototype._getEventFilterUrl = function (event) {
            try {
                if (event.stacktrace) {
                    var frames_1 = event.stacktrace.frames;
                    return this._getLastValidUrl(frames_1);
                }
                if (event.exception) {
                    var frames_2 = event.exception.values && event.exception.values[0].stacktrace && event.exception.values[0].stacktrace.frames;
                    return this._getLastValidUrl(frames_2);
                }
                return null;
            }
            catch (oO) {
                logger.error("Cannot extract url for event " + getEventDescription(event));
                return null;
            }
        };
        /**
         * @inheritDoc
         */
        InboundFilters.id = 'InboundFilters';
        return InboundFilters;
    }());



    var CoreIntegrations = /*#__PURE__*/Object.freeze({
        __proto__: null,
        FunctionToString: FunctionToString,
        InboundFilters: InboundFilters
    });

    /**
     * This was originally forked from https://github.com/occ/TraceKit, but has since been
     * largely modified and is now maintained as part of Sentry JS SDK.
     */
    // global reference to slice
    var UNKNOWN_FUNCTION = '?';
    // Chromium based browsers: Chrome, Brave, new Opera, new Edge
    var chrome = /^\s*at (?:(.*?) ?\()?((?:file|https?|blob|chrome-extension|address|native|eval|webpack|<anonymous>|[-a-z]+:|.*bundle|\/).*?)(?::(\d+))?(?::(\d+))?\)?\s*$/i;
    // gecko regex: `(?:bundle|\d+\.js)`: `bundle` is for react native, `\d+\.js` also but specifically for ram bundles because it
    // generates filenames without a prefix like `file://` the filenames in the stacktrace are just 42.js
    // We need this specific case for now because we want no other regex to match.
    var gecko = /^\s*(.*?)(?:\((.*?)\))?(?:^|@)?((?:file|https?|blob|chrome|webpack|resource|moz-extension|capacitor).*?:\/.*?|\[native code\]|[^@]*(?:bundle|\d+\.js)|\/[\w\-. /=]+)(?::(\d+))?(?::(\d+))?\s*$/i;
    var winjs = /^\s*at (?:((?:\[object object\])?.+) )?\(?((?:file|ms-appx|https?|webpack|blob):.*?):(\d+)(?::(\d+))?\)?\s*$/i;
    var geckoEval = /(\S+) line (\d+)(?: > eval line \d+)* > eval/i;
    var chromeEval = /\((\S*)(?::(\d+))(?::(\d+))\)/;
    // Based on our own mapping pattern - https://github.com/getsentry/sentry/blob/9f08305e09866c8bd6d0c24f5b0aabdd7dd6c59c/src/sentry/lang/javascript/errormapping.py#L83-L108
    var reactMinifiedRegexp = /Minified React error #\d+;/i;
    /** JSDoc */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
    function computeStackTrace(ex) {
        var stack = null;
        var popSize = 0;
        if (ex) {
            if (typeof ex.framesToPop === 'number') {
                popSize = ex.framesToPop;
            }
            else if (reactMinifiedRegexp.test(ex.message)) {
                popSize = 1;
            }
        }
        try {
            // This must be tried first because Opera 10 *destroys*
            // its stacktrace property if you try to access the stack
            // property first!!
            stack = computeStackTraceFromStacktraceProp(ex);
            if (stack) {
                return popFrames(stack, popSize);
            }
        }
        catch (e) {
            // no-empty
        }
        try {
            stack = computeStackTraceFromStackProp(ex);
            if (stack) {
                return popFrames(stack, popSize);
            }
        }
        catch (e) {
            // no-empty
        }
        return {
            message: extractMessage(ex),
            name: ex && ex.name,
            stack: [],
            failed: true,
        };
    }
    /** JSDoc */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, complexity
    function computeStackTraceFromStackProp(ex) {
        if (!ex || !ex.stack) {
            return null;
        }
        var stack = [];
        var lines = ex.stack.split('\n');
        var isEval;
        var submatch;
        var parts;
        var element;
        for (var i = 0; i < lines.length; ++i) {
            if ((parts = chrome.exec(lines[i]))) {
                var isNative = parts[2] && parts[2].indexOf('native') === 0; // start of line
                isEval = parts[2] && parts[2].indexOf('eval') === 0; // start of line
                if (isEval && (submatch = chromeEval.exec(parts[2]))) {
                    // throw out eval line/column and use top-most line/column number
                    parts[2] = submatch[1]; // url
                    parts[3] = submatch[2]; // line
                    parts[4] = submatch[3]; // column
                }
                // Arpad: Working with the regexp above is super painful. it is quite a hack, but just stripping the `address at `
                // prefix here seems like the quickest solution for now.
                var url = parts[2] && parts[2].indexOf('address at ') === 0 ? parts[2].substr('address at '.length) : parts[2];
                // Kamil: One more hack won't hurt us right? Understanding and adding more rules on top of these regexps right now
                // would be way too time consuming. (TODO: Rewrite whole RegExp to be more readable)
                var func = parts[1] || UNKNOWN_FUNCTION;
                var isSafariExtension = func.indexOf('safari-extension') !== -1;
                var isSafariWebExtension = func.indexOf('safari-web-extension') !== -1;
                if (isSafariExtension || isSafariWebExtension) {
                    func = func.indexOf('@') !== -1 ? func.split('@')[0] : UNKNOWN_FUNCTION;
                    url = isSafariExtension ? "safari-extension:" + url : "safari-web-extension:" + url;
                }
                element = {
                    url: url,
                    func: func,
                    args: isNative ? [parts[2]] : [],
                    line: parts[3] ? +parts[3] : null,
                    column: parts[4] ? +parts[4] : null,
                };
            }
            else if ((parts = winjs.exec(lines[i]))) {
                element = {
                    url: parts[2],
                    func: parts[1] || UNKNOWN_FUNCTION,
                    args: [],
                    line: +parts[3],
                    column: parts[4] ? +parts[4] : null,
                };
            }
            else if ((parts = gecko.exec(lines[i]))) {
                isEval = parts[3] && parts[3].indexOf(' > eval') > -1;
                if (isEval && (submatch = geckoEval.exec(parts[3]))) {
                    // throw out eval line/column and use top-most line number
                    parts[1] = parts[1] || "eval";
                    parts[3] = submatch[1];
                    parts[4] = submatch[2];
                    parts[5] = ''; // no column when eval
                }
                else if (i === 0 && !parts[5] && ex.columnNumber !== void 0) {
                    // FireFox uses this awesome columnNumber property for its top frame
                    // Also note, Firefox's column number is 0-based and everything else expects 1-based,
                    // so adding 1
                    // NOTE: this hack doesn't work if top-most frame is eval
                    stack[0].column = ex.columnNumber + 1;
                }
                element = {
                    url: parts[3],
                    func: parts[1] || UNKNOWN_FUNCTION,
                    args: parts[2] ? parts[2].split(',') : [],
                    line: parts[4] ? +parts[4] : null,
                    column: parts[5] ? +parts[5] : null,
                };
            }
            else {
                continue;
            }
            if (!element.func && element.line) {
                element.func = UNKNOWN_FUNCTION;
            }
            stack.push(element);
        }
        if (!stack.length) {
            return null;
        }
        return {
            message: extractMessage(ex),
            name: ex.name,
            stack: stack,
        };
    }
    /** JSDoc */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function computeStackTraceFromStacktraceProp(ex) {
        if (!ex || !ex.stacktrace) {
            return null;
        }
        // Access and store the stacktrace property before doing ANYTHING
        // else to it because Opera is not very good at providing it
        // reliably in other circumstances.
        var stacktrace = ex.stacktrace;
        var opera10Regex = / line (\d+).*script (?:in )?(\S+)(?:: in function (\S+))?$/i;
        var opera11Regex = / line (\d+), column (\d+)\s*(?:in (?:<anonymous function: ([^>]+)>|([^)]+))\((.*)\))? in (.*):\s*$/i;
        var lines = stacktrace.split('\n');
        var stack = [];
        var parts;
        for (var line = 0; line < lines.length; line += 2) {
            var element = null;
            if ((parts = opera10Regex.exec(lines[line]))) {
                element = {
                    url: parts[2],
                    func: parts[3],
                    args: [],
                    line: +parts[1],
                    column: null,
                };
            }
            else if ((parts = opera11Regex.exec(lines[line]))) {
                element = {
                    url: parts[6],
                    func: parts[3] || parts[4],
                    args: parts[5] ? parts[5].split(',') : [],
                    line: +parts[1],
                    column: +parts[2],
                };
            }
            if (element) {
                if (!element.func && element.line) {
                    element.func = UNKNOWN_FUNCTION;
                }
                stack.push(element);
            }
        }
        if (!stack.length) {
            return null;
        }
        return {
            message: extractMessage(ex),
            name: ex.name,
            stack: stack,
        };
    }
    /** Remove N number of frames from the stack */
    function popFrames(stacktrace, popSize) {
        try {
            return __assign(__assign({}, stacktrace), { stack: stacktrace.stack.slice(popSize) });
        }
        catch (e) {
            return stacktrace;
        }
    }
    /**
     * There are cases where stacktrace.message is an Event object
     * https://github.com/getsentry/sentry-javascript/issues/1949
     * In this specific case we try to extract stacktrace.message.error.message
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function extractMessage(ex) {
        var message = ex && ex.message;
        if (!message) {
            return 'No error message';
        }
        if (message.error && typeof message.error.message === 'string') {
            return message.error.message;
        }
        return message;
    }

    var STACKTRACE_LIMIT = 50;
    /**
     * This function creates an exception from an TraceKitStackTrace
     * @param stacktrace TraceKitStackTrace that will be converted to an exception
     * @hidden
     */
    function exceptionFromStacktrace(stacktrace) {
        var frames = prepareFramesForEvent(stacktrace.stack);
        var exception = {
            type: stacktrace.name,
            value: stacktrace.message,
        };
        if (frames && frames.length) {
            exception.stacktrace = { frames: frames };
        }
        if (exception.type === undefined && exception.value === '') {
            exception.value = 'Unrecoverable error caught';
        }
        return exception;
    }
    /**
     * @hidden
     */
    function eventFromPlainObject(exception, syntheticException, rejection) {
        var event = {
            exception: {
                values: [
                    {
                        type: isEvent(exception) ? exception.constructor.name : rejection ? 'UnhandledRejection' : 'Error',
                        value: "Non-Error " + (rejection ? 'promise rejection' : 'exception') + " captured with keys: " + extractExceptionKeysForMessage(exception),
                    },
                ],
            },
            extra: {
                __serialized__: normalizeToSize(exception),
            },
        };
        if (syntheticException) {
            var stacktrace = computeStackTrace(syntheticException);
            var frames_1 = prepareFramesForEvent(stacktrace.stack);
            event.stacktrace = {
                frames: frames_1,
            };
        }
        return event;
    }
    /**
     * @hidden
     */
    function eventFromStacktrace(stacktrace) {
        var exception = exceptionFromStacktrace(stacktrace);
        return {
            exception: {
                values: [exception],
            },
        };
    }
    /**
     * @hidden
     */
    function prepareFramesForEvent(stack) {
        if (!stack || !stack.length) {
            return [];
        }
        var localStack = stack;
        var firstFrameFunction = localStack[0].func || '';
        var lastFrameFunction = localStack[localStack.length - 1].func || '';
        // If stack starts with one of our API calls, remove it (starts, meaning it's the top of the stack - aka last call)
        if (firstFrameFunction.indexOf('captureMessage') !== -1 || firstFrameFunction.indexOf('captureException') !== -1) {
            localStack = localStack.slice(1);
        }
        // If stack ends with one of our internal API calls, remove it (ends, meaning it's the bottom of the stack - aka top-most call)
        if (lastFrameFunction.indexOf('sentryWrapped') !== -1) {
            localStack = localStack.slice(0, -1);
        }
        // The frame where the crash happened, should be the last entry in the array
        return localStack
            .slice(0, STACKTRACE_LIMIT)
            .map(function (frame) { return ({
            colno: frame.column === null ? undefined : frame.column,
            filename: frame.url || localStack[0].url,
            function: frame.func || '?',
            in_app: true,
            lineno: frame.line === null ? undefined : frame.line,
        }); })
            .reverse();
    }

    /**
     * Builds and Event from a Exception
     * @hidden
     */
    function eventFromException(options, exception, hint) {
        var syntheticException = (hint && hint.syntheticException) || undefined;
        var event = eventFromUnknownInput(exception, syntheticException, {
            attachStacktrace: options.attachStacktrace,
        });
        addExceptionMechanism(event, {
            handled: true,
            type: 'generic',
        });
        event.level = exports.Severity.Error;
        if (hint && hint.event_id) {
            event.event_id = hint.event_id;
        }
        return SyncPromise.resolve(event);
    }
    /**
     * Builds and Event from a Message
     * @hidden
     */
    function eventFromMessage(options, message, level, hint) {
        if (level === void 0) { level = exports.Severity.Info; }
        var syntheticException = (hint && hint.syntheticException) || undefined;
        var event = eventFromString(message, syntheticException, {
            attachStacktrace: options.attachStacktrace,
        });
        event.level = level;
        if (hint && hint.event_id) {
            event.event_id = hint.event_id;
        }
        return SyncPromise.resolve(event);
    }
    /**
     * @hidden
     */
    function eventFromUnknownInput(exception, syntheticException, options) {
        if (options === void 0) { options = {}; }
        var event;
        if (isErrorEvent(exception) && exception.error) {
            // If it is an ErrorEvent with `error` property, extract it to get actual Error
            var errorEvent = exception;
            // eslint-disable-next-line no-param-reassign
            exception = errorEvent.error;
            event = eventFromStacktrace(computeStackTrace(exception));
            return event;
        }
        if (isDOMError(exception) || isDOMException(exception)) {
            // If it is a DOMError or DOMException (which are legacy APIs, but still supported in some browsers)
            // then we just extract the name, code, and message, as they don't provide anything else
            // https://developer.mozilla.org/en-US/docs/Web/API/DOMError
            // https://developer.mozilla.org/en-US/docs/Web/API/DOMException
            var domException = exception;
            var name_1 = domException.name || (isDOMError(domException) ? 'DOMError' : 'DOMException');
            var message = domException.message ? name_1 + ": " + domException.message : name_1;
            event = eventFromString(message, syntheticException, options);
            addExceptionTypeValue(event, message);
            if ('code' in domException) {
                event.tags = __assign(__assign({}, event.tags), { 'DOMException.code': "" + domException.code });
            }
            return event;
        }
        if (isError(exception)) {
            // we have a real Error object, do nothing
            event = eventFromStacktrace(computeStackTrace(exception));
            return event;
        }
        if (isPlainObject(exception) || isEvent(exception)) {
            // If it is plain Object or Event, serialize it manually and extract options
            // This will allow us to group events based on top-level keys
            // which is much better than creating new group when any key/value change
            var objectException = exception;
            event = eventFromPlainObject(objectException, syntheticException, options.rejection);
            addExceptionMechanism(event, {
                synthetic: true,
            });
            return event;
        }
        // If none of previous checks were valid, then it means that it's not:
        // - an instance of DOMError
        // - an instance of DOMException
        // - an instance of Event
        // - an instance of Error
        // - a valid ErrorEvent (one with an error property)
        // - a plain Object
        //
        // So bail out and capture it as a simple message:
        event = eventFromString(exception, syntheticException, options);
        addExceptionTypeValue(event, "" + exception, undefined);
        addExceptionMechanism(event, {
            synthetic: true,
        });
        return event;
    }
    /**
     * @hidden
     */
    function eventFromString(input, syntheticException, options) {
        if (options === void 0) { options = {}; }
        var event = {
            message: input,
        };
        if (options.attachStacktrace && syntheticException) {
            var stacktrace = computeStackTrace(syntheticException);
            var frames_1 = prepareFramesForEvent(stacktrace.stack);
            event.stacktrace = {
                frames: frames_1,
            };
        }
        return event;
    }

    var CATEGORY_MAPPING = {
        event: 'error',
        transaction: 'transaction',
        session: 'session',
        attachment: 'attachment',
    };
    /** Base Transport class implementation */
    var BaseTransport = /** @class */ (function () {
        function BaseTransport(options) {
            this.options = options;
            /** A simple buffer holding all requests. */
            this._buffer = new PromiseBuffer(30);
            /** Locks transport after receiving rate limits in a response */
            this._rateLimits = {};
            this._api = new API(options.dsn, options._metadata, options.tunnel);
            // eslint-disable-next-line deprecation/deprecation
            this.url = this._api.getStoreEndpointWithUrlEncodedAuth();
        }
        /**
         * @inheritDoc
         */
        BaseTransport.prototype.sendEvent = function (_) {
            throw new SentryError('Transport Class has to implement `sendEvent` method');
        };
        /**
         * @inheritDoc
         */
        BaseTransport.prototype.close = function (timeout) {
            return this._buffer.drain(timeout);
        };
        /**
         * Handle Sentry repsonse for promise-based transports.
         */
        BaseTransport.prototype._handleResponse = function (_a) {
            var requestType = _a.requestType, response = _a.response, headers = _a.headers, resolve = _a.resolve, reject = _a.reject;
            var status = exports.Status.fromHttpCode(response.status);
            /**
             * "The name is case-insensitive."
             * https://developer.mozilla.org/en-US/docs/Web/API/Headers/get
             */
            var limited = this._handleRateLimit(headers);
            if (limited)
                logger.warn("Too many " + requestType + " requests, backing off until: " + this._disabledUntil(requestType));
            if (status === exports.Status.Success) {
                resolve({ status: status });
                return;
            }
            reject(response);
        };
        /**
         * Gets the time that given category is disabled until for rate limiting
         */
        BaseTransport.prototype._disabledUntil = function (requestType) {
            var category = CATEGORY_MAPPING[requestType];
            return this._rateLimits[category] || this._rateLimits.all;
        };
        /**
         * Checks if a category is rate limited
         */
        BaseTransport.prototype._isRateLimited = function (requestType) {
            return this._disabledUntil(requestType) > new Date(Date.now());
        };
        /**
         * Sets internal _rateLimits from incoming headers. Returns true if headers contains a non-empty rate limiting header.
         */
        BaseTransport.prototype._handleRateLimit = function (headers) {
            var e_1, _a, e_2, _b;
            var now = Date.now();
            var rlHeader = headers['x-sentry-rate-limits'];
            var raHeader = headers['retry-after'];
            if (rlHeader) {
                try {
                    // rate limit headers are of the form
                    //     <header>,<header>,..
                    // where each <header> is of the form
                    //     <retry_after>: <categories>: <scope>: <reason_code>
                    // where
                    //     <retry_after> is a delay in ms
                    //     <categories> is the event type(s) (error, transaction, etc) being rate limited and is of the form
                    //         <category>;<category>;...
                    //     <scope> is what's being limited (org, project, or key) - ignored by SDK
                    //     <reason_code> is an arbitrary string like "org_quota" - ignored by SDK
                    for (var _c = __values(rlHeader.trim().split(',')), _d = _c.next(); !_d.done; _d = _c.next()) {
                        var limit = _d.value;
                        var parameters = limit.split(':', 2);
                        var headerDelay = parseInt(parameters[0], 10);
                        var delay = (!isNaN(headerDelay) ? headerDelay : 60) * 1000; // 60sec default
                        try {
                            for (var _e = (e_2 = void 0, __values(parameters[1].split(';'))), _f = _e.next(); !_f.done; _f = _e.next()) {
                                var category = _f.value;
                                this._rateLimits[category || 'all'] = new Date(now + delay);
                            }
                        }
                        catch (e_2_1) { e_2 = { error: e_2_1 }; }
                        finally {
                            try {
                                if (_f && !_f.done && (_b = _e.return)) _b.call(_e);
                            }
                            finally { if (e_2) throw e_2.error; }
                        }
                    }
                }
                catch (e_1_1) { e_1 = { error: e_1_1 }; }
                finally {
                    try {
                        if (_d && !_d.done && (_a = _c.return)) _a.call(_c);
                    }
                    finally { if (e_1) throw e_1.error; }
                }
                return true;
            }
            else if (raHeader) {
                this._rateLimits.all = new Date(now + parseRetryAfterHeader(now, raHeader));
                return true;
            }
            return false;
        };
        return BaseTransport;
    }());

    /**
     * A special usecase for incorrectly wrapped Fetch APIs in conjunction with ad-blockers.
     * Whenever someone wraps the Fetch API and returns the wrong promise chain,
     * this chain becomes orphaned and there is no possible way to capture it's rejections
     * other than allowing it bubble up to this very handler. eg.
     *
     * const f = window.fetch;
     * window.fetch = function () {
     *   const p = f.apply(this, arguments);
     *
     *   p.then(function() {
     *     console.log('hi.');
     *   });
     *
     *   return p;
     * }
     *
     * `p.then(function () { ... })` is producing a completely separate promise chain,
     * however, what's returned is `p` - the result of original `fetch` call.
     *
     * This mean, that whenever we use the Fetch API to send our own requests, _and_
     * some ad-blocker blocks it, this orphaned chain will _always_ reject,
     * effectively causing another event to be captured.
     * This makes a whole process become an infinite loop, which we need to somehow
     * deal with, and break it in one way or another.
     *
     * To deal with this issue, we are making sure that we _always_ use the real
     * browser Fetch API, instead of relying on what `window.fetch` exposes.
     * The only downside to this would be missing our own requests as breadcrumbs,
     * but because we are already not doing this, it should be just fine.
     *
     * Possible failed fetch error messages per-browser:
     *
     * Chrome:  Failed to fetch
     * Edge:    Failed to Fetch
     * Firefox: NetworkError when attempting to fetch resource
     * Safari:  resource blocked by content blocker
     */
    function getNativeFetchImplementation() {
        /* eslint-disable @typescript-eslint/unbound-method */
        var _a, _b;
        // Fast path to avoid DOM I/O
        var global = getGlobalObject();
        if (isNativeFetch(global.fetch)) {
            return global.fetch.bind(global);
        }
        var document = global.document;
        var fetchImpl = global.fetch;
        // eslint-disable-next-line deprecation/deprecation
        if (typeof ((_a = document) === null || _a === void 0 ? void 0 : _a.createElement) === "function") {
            try {
                var sandbox = document.createElement('iframe');
                sandbox.hidden = true;
                document.head.appendChild(sandbox);
                if ((_b = sandbox.contentWindow) === null || _b === void 0 ? void 0 : _b.fetch) {
                    fetchImpl = sandbox.contentWindow.fetch;
                }
                document.head.removeChild(sandbox);
            }
            catch (e) {
                logger.warn('Could not create sandbox iframe for pure fetch check, bailing to window.fetch: ', e);
            }
        }
        return fetchImpl.bind(global);
        /* eslint-enable @typescript-eslint/unbound-method */
    }
    /** `fetch` based transport */
    var FetchTransport = /** @class */ (function (_super) {
        __extends(FetchTransport, _super);
        function FetchTransport(options, fetchImpl) {
            if (fetchImpl === void 0) { fetchImpl = getNativeFetchImplementation(); }
            var _this = _super.call(this, options) || this;
            _this._fetch = fetchImpl;
            return _this;
        }
        /**
         * @inheritDoc
         */
        FetchTransport.prototype.sendEvent = function (event) {
            return this._sendRequest(eventToSentryRequest(event, this._api), event);
        };
        /**
         * @inheritDoc
         */
        FetchTransport.prototype.sendSession = function (session) {
            return this._sendRequest(sessionToSentryRequest(session, this._api), session);
        };
        /**
         * @param sentryRequest Prepared SentryRequest to be delivered
         * @param originalPayload Original payload used to create SentryRequest
         */
        FetchTransport.prototype._sendRequest = function (sentryRequest, originalPayload) {
            var _this = this;
            if (this._isRateLimited(sentryRequest.type)) {
                return Promise.reject({
                    event: originalPayload,
                    type: sentryRequest.type,
                    reason: "Transport for " + sentryRequest.type + " requests locked till " + this._disabledUntil(sentryRequest.type) + " due to too many requests.",
                    status: 429,
                });
            }
            var options = {
                body: sentryRequest.body,
                method: 'POST',
                // Despite all stars in the sky saying that Edge supports old draft syntax, aka 'never', 'always', 'origin' and 'default
                // https://caniuse.com/#feat=referrer-policy
                // It doesn't. And it throw exception instead of ignoring this parameter...
                // REF: https://github.com/getsentry/raven-js/issues/1233
                referrerPolicy: (supportsReferrerPolicy() ? 'origin' : ''),
            };
            if (this.options.fetchParameters !== undefined) {
                Object.assign(options, this.options.fetchParameters);
            }
            if (this.options.headers !== undefined) {
                options.headers = this.options.headers;
            }
            return this._buffer.add(function () {
                return new SyncPromise(function (resolve, reject) {
                    void _this._fetch(sentryRequest.url, options)
                        .then(function (response) {
                        var headers = {
                            'x-sentry-rate-limits': response.headers.get('X-Sentry-Rate-Limits'),
                            'retry-after': response.headers.get('Retry-After'),
                        };
                        _this._handleResponse({
                            requestType: sentryRequest.type,
                            response: response,
                            headers: headers,
                            resolve: resolve,
                            reject: reject,
                        });
                    })
                        .catch(reject);
                });
            });
        };
        return FetchTransport;
    }(BaseTransport));

    /** `XHR` based transport */
    var XHRTransport = /** @class */ (function (_super) {
        __extends(XHRTransport, _super);
        function XHRTransport() {
            return _super !== null && _super.apply(this, arguments) || this;
        }
        /**
         * @inheritDoc
         */
        XHRTransport.prototype.sendEvent = function (event) {
            return this._sendRequest(eventToSentryRequest(event, this._api), event);
        };
        /**
         * @inheritDoc
         */
        XHRTransport.prototype.sendSession = function (session) {
            return this._sendRequest(sessionToSentryRequest(session, this._api), session);
        };
        /**
         * @param sentryRequest Prepared SentryRequest to be delivered
         * @param originalPayload Original payload used to create SentryRequest
         */
        XHRTransport.prototype._sendRequest = function (sentryRequest, originalPayload) {
            var _this = this;
            if (this._isRateLimited(sentryRequest.type)) {
                return Promise.reject({
                    event: originalPayload,
                    type: sentryRequest.type,
                    reason: "Transport for " + sentryRequest.type + " requests locked till " + this._disabledUntil(sentryRequest.type) + " due to too many requests.",
                    status: 429,
                });
            }
            return this._buffer.add(function () {
                return new SyncPromise(function (resolve, reject) {
                    var request = new XMLHttpRequest();
                    request.onreadystatechange = function () {
                        if (request.readyState === 4) {
                            var headers = {
                                'x-sentry-rate-limits': request.getResponseHeader('X-Sentry-Rate-Limits'),
                                'retry-after': request.getResponseHeader('Retry-After'),
                            };
                            _this._handleResponse({ requestType: sentryRequest.type, response: request, headers: headers, resolve: resolve, reject: reject });
                        }
                    };
                    request.open('POST', sentryRequest.url);
                    for (var header in _this.options.headers) {
                        if (_this.options.headers.hasOwnProperty(header)) {
                            request.setRequestHeader(header, _this.options.headers[header]);
                        }
                    }
                    request.send(sentryRequest.body);
                });
            });
        };
        return XHRTransport;
    }(BaseTransport));



    var index = /*#__PURE__*/Object.freeze({
        __proto__: null,
        BaseTransport: BaseTransport,
        FetchTransport: FetchTransport,
        XHRTransport: XHRTransport
    });

    /**
     * The Sentry Browser SDK Backend.
     * @hidden
     */
    var BrowserBackend = /** @class */ (function (_super) {
        __extends(BrowserBackend, _super);
        function BrowserBackend() {
            return _super !== null && _super.apply(this, arguments) || this;
        }
        /**
         * @inheritDoc
         */
        BrowserBackend.prototype.eventFromException = function (exception, hint) {
            return eventFromException(this._options, exception, hint);
        };
        /**
         * @inheritDoc
         */
        BrowserBackend.prototype.eventFromMessage = function (message, level, hint) {
            if (level === void 0) { level = exports.Severity.Info; }
            return eventFromMessage(this._options, message, level, hint);
        };
        /**
         * @inheritDoc
         */
        BrowserBackend.prototype._setupTransport = function () {
            if (!this._options.dsn) {
                // We return the noop transport here in case there is no Dsn.
                return _super.prototype._setupTransport.call(this);
            }
            var transportOptions = __assign(__assign({}, this._options.transportOptions), { dsn: this._options.dsn, tunnel: this._options.tunnel, _metadata: this._options._metadata });
            if (this._options.transport) {
                return new this._options.transport(transportOptions);
            }
            if (supportsFetch()) {
                return new FetchTransport(transportOptions);
            }
            return new XHRTransport(transportOptions);
        };
        return BrowserBackend;
    }(BaseBackend));

    var ignoreOnError = 0;
    /**
     * @hidden
     */
    function shouldIgnoreOnError() {
        return ignoreOnError > 0;
    }
    /**
     * @hidden
     */
    function ignoreNextOnError() {
        // onerror should trigger before setTimeout
        ignoreOnError += 1;
        setTimeout(function () {
            ignoreOnError -= 1;
        });
    }
    /**
     * Instruments the given function and sends an event to Sentry every time the
     * function throws an exception.
     *
     * @param fn A function to wrap.
     * @returns The wrapped function.
     * @hidden
     */
    function wrap(fn, options, before) {
        if (options === void 0) { options = {}; }
        if (typeof fn !== 'function') {
            return fn;
        }
        try {
            // We don't wanna wrap it twice
            if (fn.__sentry__) {
                return fn;
            }
            // If this has already been wrapped in the past, return that wrapped function
            if (fn.__sentry_wrapped__) {
                return fn.__sentry_wrapped__;
            }
        }
        catch (e) {
            // Just accessing custom props in some Selenium environments
            // can cause a "Permission denied" exception (see raven-js#495).
            // Bail on wrapping and return the function as-is (defers to window.onerror).
            return fn;
        }
        /* eslint-disable prefer-rest-params */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        var sentryWrapped = function () {
            var args = Array.prototype.slice.call(arguments);
            try {
                if (before && typeof before === 'function') {
                    before.apply(this, arguments);
                }
                // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access
                var wrappedArguments = args.map(function (arg) { return wrap(arg, options); });
                if (fn.handleEvent) {
                    // Attempt to invoke user-land function
                    // NOTE: If you are a Sentry user, and you are seeing this stack frame, it
                    //       means the sentry.javascript SDK caught an error invoking your application code. This
                    //       is expected behavior and NOT indicative of a bug with sentry.javascript.
                    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                    return fn.handleEvent.apply(this, wrappedArguments);
                }
                // Attempt to invoke user-land function
                // NOTE: If you are a Sentry user, and you are seeing this stack frame, it
                //       means the sentry.javascript SDK caught an error invoking your application code. This
                //       is expected behavior and NOT indicative of a bug with sentry.javascript.
                return fn.apply(this, wrappedArguments);
            }
            catch (ex) {
                ignoreNextOnError();
                withScope(function (scope) {
                    scope.addEventProcessor(function (event) {
                        var processedEvent = __assign({}, event);
                        if (options.mechanism) {
                            addExceptionTypeValue(processedEvent, undefined, undefined);
                            addExceptionMechanism(processedEvent, options.mechanism);
                        }
                        processedEvent.extra = __assign(__assign({}, processedEvent.extra), { arguments: args });
                        return processedEvent;
                    });
                    captureException(ex);
                });
                throw ex;
            }
        };
        /* eslint-enable prefer-rest-params */
        // Accessing some objects may throw
        // ref: https://github.com/getsentry/sentry-javascript/issues/1168
        try {
            for (var property in fn) {
                if (Object.prototype.hasOwnProperty.call(fn, property)) {
                    sentryWrapped[property] = fn[property];
                }
            }
        }
        catch (_oO) { } // eslint-disable-line no-empty
        fn.prototype = fn.prototype || {};
        sentryWrapped.prototype = fn.prototype;
        Object.defineProperty(fn, '__sentry_wrapped__', {
            enumerable: false,
            value: sentryWrapped,
        });
        // Signal that this function has been wrapped/filled already
        // for both debugging and to prevent it to being wrapped/filled twice
        Object.defineProperties(sentryWrapped, {
            __sentry__: {
                enumerable: false,
                value: true,
            },
            __sentry_original__: {
                enumerable: false,
                value: fn,
            },
        });
        // Restore original function name (not all browsers allow that)
        try {
            var descriptor = Object.getOwnPropertyDescriptor(sentryWrapped, 'name');
            if (descriptor.configurable) {
                Object.defineProperty(sentryWrapped, 'name', {
                    get: function () {
                        return fn.name;
                    },
                });
            }
            // eslint-disable-next-line no-empty
        }
        catch (_oO) { }
        return sentryWrapped;
    }
    /**
     * Injects the Report Dialog script
     * @hidden
     */
    function injectReportDialog(options) {
        if (options === void 0) { options = {}; }
        if (!options.eventId) {
            logger.error("Missing eventId option in showReportDialog call");
            return;
        }
        if (!options.dsn) {
            logger.error("Missing dsn option in showReportDialog call");
            return;
        }
        var script = document.createElement('script');
        script.async = true;
        script.src = new API(options.dsn).getReportDialogEndpoint(options);
        if (options.onLoad) {
            // eslint-disable-next-line @typescript-eslint/unbound-method
            script.onload = options.onLoad;
        }
        (document.head || document.body).appendChild(script);
    }

    /** Global handlers */
    var GlobalHandlers = /** @class */ (function () {
        /** JSDoc */
        function GlobalHandlers(options) {
            /**
             * @inheritDoc
             */
            this.name = GlobalHandlers.id;
            /** JSDoc */
            this._onErrorHandlerInstalled = false;
            /** JSDoc */
            this._onUnhandledRejectionHandlerInstalled = false;
            this._options = __assign({ onerror: true, onunhandledrejection: true }, options);
        }
        /**
         * @inheritDoc
         */
        GlobalHandlers.prototype.setupOnce = function () {
            Error.stackTraceLimit = 50;
            if (this._options.onerror) {
                logger.log('Global Handler attached: onerror');
                this._installGlobalOnErrorHandler();
            }
            if (this._options.onunhandledrejection) {
                logger.log('Global Handler attached: onunhandledrejection');
                this._installGlobalOnUnhandledRejectionHandler();
            }
        };
        /** JSDoc */
        GlobalHandlers.prototype._installGlobalOnErrorHandler = function () {
            var _this = this;
            if (this._onErrorHandlerInstalled) {
                return;
            }
            addInstrumentationHandler({
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                callback: function (data) {
                    var error = data.error;
                    var currentHub = getCurrentHub();
                    var hasIntegration = currentHub.getIntegration(GlobalHandlers);
                    var isFailedOwnDelivery = error && error.__sentry_own_request__ === true;
                    if (!hasIntegration || shouldIgnoreOnError() || isFailedOwnDelivery) {
                        return;
                    }
                    var client = currentHub.getClient();
                    var event = error === undefined && isString(data.msg)
                        ? _this._eventFromIncompleteOnError(data.msg, data.url, data.line, data.column)
                        : _this._enhanceEventWithInitialFrame(eventFromUnknownInput(error || data.msg, undefined, {
                            attachStacktrace: client && client.getOptions().attachStacktrace,
                            rejection: false,
                        }), data.url, data.line, data.column);
                    addExceptionMechanism(event, {
                        handled: false,
                        type: 'onerror',
                    });
                    currentHub.captureEvent(event, {
                        originalException: error,
                    });
                },
                type: 'error',
            });
            this._onErrorHandlerInstalled = true;
        };
        /** JSDoc */
        GlobalHandlers.prototype._installGlobalOnUnhandledRejectionHandler = function () {
            var _this = this;
            if (this._onUnhandledRejectionHandlerInstalled) {
                return;
            }
            addInstrumentationHandler({
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                callback: function (e) {
                    var error = e;
                    // dig the object of the rejection out of known event types
                    try {
                        // PromiseRejectionEvents store the object of the rejection under 'reason'
                        // see https://developer.mozilla.org/en-US/docs/Web/API/PromiseRejectionEvent
                        if ('reason' in e) {
                            error = e.reason;
                        }
                        // something, somewhere, (likely a browser extension) effectively casts PromiseRejectionEvents
                        // to CustomEvents, moving the `promise` and `reason` attributes of the PRE into
                        // the CustomEvent's `detail` attribute, since they're not part of CustomEvent's spec
                        // see https://developer.mozilla.org/en-US/docs/Web/API/CustomEvent and
                        // https://github.com/getsentry/sentry-javascript/issues/2380
                        else if ('detail' in e && 'reason' in e.detail) {
                            error = e.detail.reason;
                        }
                    }
                    catch (_oO) {
                        // no-empty
                    }
                    var currentHub = getCurrentHub();
                    var hasIntegration = currentHub.getIntegration(GlobalHandlers);
                    var isFailedOwnDelivery = error && error.__sentry_own_request__ === true;
                    if (!hasIntegration || shouldIgnoreOnError() || isFailedOwnDelivery) {
                        return true;
                    }
                    var client = currentHub.getClient();
                    var event = isPrimitive(error)
                        ? _this._eventFromRejectionWithPrimitive(error)
                        : eventFromUnknownInput(error, undefined, {
                            attachStacktrace: client && client.getOptions().attachStacktrace,
                            rejection: true,
                        });
                    event.level = exports.Severity.Error;
                    addExceptionMechanism(event, {
                        handled: false,
                        type: 'onunhandledrejection',
                    });
                    currentHub.captureEvent(event, {
                        originalException: error,
                    });
                    return;
                },
                type: 'unhandledrejection',
            });
            this._onUnhandledRejectionHandlerInstalled = true;
        };
        /**
         * This function creates a stack from an old, error-less onerror handler.
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        GlobalHandlers.prototype._eventFromIncompleteOnError = function (msg, url, line, column) {
            var ERROR_TYPES_RE = /^(?:[Uu]ncaught (?:exception: )?)?(?:((?:Eval|Internal|Range|Reference|Syntax|Type|URI|)Error): )?(.*)$/i;
            // If 'message' is ErrorEvent, get real message from inside
            var message = isErrorEvent(msg) ? msg.message : msg;
            var name;
            var groups = message.match(ERROR_TYPES_RE);
            if (groups) {
                name = groups[1];
                message = groups[2];
            }
            var event = {
                exception: {
                    values: [
                        {
                            type: name || 'Error',
                            value: message,
                        },
                    ],
                },
            };
            return this._enhanceEventWithInitialFrame(event, url, line, column);
        };
        /**
         * Create an event from a promise rejection where the `reason` is a primitive.
         *
         * @param reason: The `reason` property of the promise rejection
         * @returns An Event object with an appropriate `exception` value
         */
        GlobalHandlers.prototype._eventFromRejectionWithPrimitive = function (reason) {
            return {
                exception: {
                    values: [
                        {
                            type: 'UnhandledRejection',
                            // String() is needed because the Primitive type includes symbols (which can't be automatically stringified)
                            value: "Non-Error promise rejection captured with value: " + String(reason),
                        },
                    ],
                },
            };
        };
        /** JSDoc */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        GlobalHandlers.prototype._enhanceEventWithInitialFrame = function (event, url, line, column) {
            event.exception = event.exception || {};
            event.exception.values = event.exception.values || [];
            event.exception.values[0] = event.exception.values[0] || {};
            event.exception.values[0].stacktrace = event.exception.values[0].stacktrace || {};
            event.exception.values[0].stacktrace.frames = event.exception.values[0].stacktrace.frames || [];
            var colno = isNaN(parseInt(column, 10)) ? undefined : column;
            var lineno = isNaN(parseInt(line, 10)) ? undefined : line;
            var filename = isString(url) && url.length > 0 ? url : getLocationHref();
            if (event.exception.values[0].stacktrace.frames.length === 0) {
                event.exception.values[0].stacktrace.frames.push({
                    colno: colno,
                    filename: filename,
                    function: '?',
                    in_app: true,
                    lineno: lineno,
                });
            }
            return event;
        };
        /**
         * @inheritDoc
         */
        GlobalHandlers.id = 'GlobalHandlers';
        return GlobalHandlers;
    }());

    var DEFAULT_EVENT_TARGET = [
        'EventTarget',
        'Window',
        'Node',
        'ApplicationCache',
        'AudioTrackList',
        'ChannelMergerNode',
        'CryptoOperation',
        'EventSource',
        'FileReader',
        'HTMLUnknownElement',
        'IDBDatabase',
        'IDBRequest',
        'IDBTransaction',
        'KeyOperation',
        'MediaController',
        'MessagePort',
        'ModalWindow',
        'Notification',
        'SVGElementInstance',
        'Screen',
        'TextTrack',
        'TextTrackCue',
        'TextTrackList',
        'WebSocket',
        'WebSocketWorker',
        'Worker',
        'XMLHttpRequest',
        'XMLHttpRequestEventTarget',
        'XMLHttpRequestUpload',
    ];
    /** Wrap timer functions and event targets to catch errors and provide better meta data */
    var TryCatch = /** @class */ (function () {
        /**
         * @inheritDoc
         */
        function TryCatch(options) {
            /**
             * @inheritDoc
             */
            this.name = TryCatch.id;
            this._options = __assign({ XMLHttpRequest: true, eventTarget: true, requestAnimationFrame: true, setInterval: true, setTimeout: true }, options);
        }
        /**
         * Wrap timer functions and event targets to catch errors
         * and provide better metadata.
         */
        TryCatch.prototype.setupOnce = function () {
            var global = getGlobalObject();
            if (this._options.setTimeout) {
                fill(global, 'setTimeout', this._wrapTimeFunction.bind(this));
            }
            if (this._options.setInterval) {
                fill(global, 'setInterval', this._wrapTimeFunction.bind(this));
            }
            if (this._options.requestAnimationFrame) {
                fill(global, 'requestAnimationFrame', this._wrapRAF.bind(this));
            }
            if (this._options.XMLHttpRequest && 'XMLHttpRequest' in global) {
                fill(XMLHttpRequest.prototype, 'send', this._wrapXHR.bind(this));
            }
            if (this._options.eventTarget) {
                var eventTarget = Array.isArray(this._options.eventTarget) ? this._options.eventTarget : DEFAULT_EVENT_TARGET;
                eventTarget.forEach(this._wrapEventTarget.bind(this));
            }
        };
        /** JSDoc */
        TryCatch.prototype._wrapTimeFunction = function (original) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                var originalCallback = args[0];
                args[0] = wrap(originalCallback, {
                    mechanism: {
                        data: { function: getFunctionName(original) },
                        handled: true,
                        type: 'instrument',
                    },
                });
                return original.apply(this, args);
            };
        };
        /** JSDoc */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        TryCatch.prototype._wrapRAF = function (original) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return function (callback) {
                // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                return original.call(this, wrap(callback, {
                    mechanism: {
                        data: {
                            function: 'requestAnimationFrame',
                            handler: getFunctionName(original),
                        },
                        handled: true,
                        type: 'instrument',
                    },
                }));
            };
        };
        /** JSDoc */
        TryCatch.prototype._wrapEventTarget = function (target) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            var global = getGlobalObject();
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            var proto = global[target] && global[target].prototype;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            if (!proto || !proto.hasOwnProperty || !proto.hasOwnProperty('addEventListener')) {
                return;
            }
            fill(proto, 'addEventListener', function (original) {
                return function (eventName, fn, options) {
                    try {
                        if (typeof fn.handleEvent === 'function') {
                            fn.handleEvent = wrap(fn.handleEvent.bind(fn), {
                                mechanism: {
                                    data: {
                                        function: 'handleEvent',
                                        handler: getFunctionName(fn),
                                        target: target,
                                    },
                                    handled: true,
                                    type: 'instrument',
                                },
                            });
                        }
                    }
                    catch (err) {
                        // can sometimes get 'Permission denied to access property "handle Event'
                    }
                    return original.call(this, eventName, 
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    wrap(fn, {
                        mechanism: {
                            data: {
                                function: 'addEventListener',
                                handler: getFunctionName(fn),
                                target: target,
                            },
                            handled: true,
                            type: 'instrument',
                        },
                    }), options);
                };
            });
            fill(proto, 'removeEventListener', function (originalRemoveEventListener) {
                return function (eventName, fn, options) {
                    var _a;
                    /**
                     * There are 2 possible scenarios here:
                     *
                     * 1. Someone passes a callback, which was attached prior to Sentry initialization, or by using unmodified
                     * method, eg. `document.addEventListener.call(el, name, handler). In this case, we treat this function
                     * as a pass-through, and call original `removeEventListener` with it.
                     *
                     * 2. Someone passes a callback, which was attached after Sentry was initialized, which means that it was using
                     * our wrapped version of `addEventListener`, which internally calls `wrap` helper.
                     * This helper "wraps" whole callback inside a try/catch statement, and attached appropriate metadata to it,
                     * in order for us to make a distinction between wrapped/non-wrapped functions possible.
                     * If a function was wrapped, it has additional property of `__sentry_wrapped__`, holding the handler.
                     *
                     * When someone adds a handler prior to initialization, and then do it again, but after,
                     * then we have to detach both of them. Otherwise, if we'd detach only wrapped one, it'd be impossible
                     * to get rid of the initial handler and it'd stick there forever.
                     */
                    var wrappedEventHandler = fn;
                    try {
                        var originalEventHandler = (_a = wrappedEventHandler) === null || _a === void 0 ? void 0 : _a.__sentry_wrapped__;
                        if (originalEventHandler) {
                            originalRemoveEventListener.call(this, eventName, originalEventHandler, options);
                        }
                    }
                    catch (e) {
                        // ignore, accessing __sentry_wrapped__ will throw in some Selenium environments
                    }
                    return originalRemoveEventListener.call(this, eventName, wrappedEventHandler, options);
                };
            });
        };
        /** JSDoc */
        TryCatch.prototype._wrapXHR = function (originalSend) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                // eslint-disable-next-line @typescript-eslint/no-this-alias
                var xhr = this;
                var xmlHttpRequestProps = ['onload', 'onerror', 'onprogress', 'onreadystatechange'];
                xmlHttpRequestProps.forEach(function (prop) {
                    if (prop in xhr && typeof xhr[prop] === 'function') {
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        fill(xhr, prop, function (original) {
                            var wrapOptions = {
                                mechanism: {
                                    data: {
                                        function: prop,
                                        handler: getFunctionName(original),
                                    },
                                    handled: true,
                                    type: 'instrument',
                                },
                            };
                            // If Instrument integration has been called before TryCatch, get the name of original function
                            if (original.__sentry_original__) {
                                wrapOptions.mechanism.data.handler = getFunctionName(original.__sentry_original__);
                            }
                            // Otherwise wrap directly
                            return wrap(original, wrapOptions);
                        });
                    }
                });
                return originalSend.apply(this, args);
            };
        };
        /**
         * @inheritDoc
         */
        TryCatch.id = 'TryCatch';
        return TryCatch;
    }());

    /**
     * Default Breadcrumbs instrumentations
     * TODO: Deprecated - with v6, this will be renamed to `Instrument`
     */
    var Breadcrumbs = /** @class */ (function () {
        /**
         * @inheritDoc
         */
        function Breadcrumbs(options) {
            /**
             * @inheritDoc
             */
            this.name = Breadcrumbs.id;
            this._options = __assign({ console: true, dom: true, fetch: true, history: true, sentry: true, xhr: true }, options);
        }
        /**
         * Create a breadcrumb of `sentry` from the events themselves
         */
        Breadcrumbs.prototype.addSentryBreadcrumb = function (event) {
            if (!this._options.sentry) {
                return;
            }
            getCurrentHub().addBreadcrumb({
                category: "sentry." + (event.type === 'transaction' ? 'transaction' : 'event'),
                event_id: event.event_id,
                level: event.level,
                message: getEventDescription(event),
            }, {
                event: event,
            });
        };
        /**
         * Instrument browser built-ins w/ breadcrumb capturing
         *  - Console API
         *  - DOM API (click/typing)
         *  - XMLHttpRequest API
         *  - Fetch API
         *  - History API
         */
        Breadcrumbs.prototype.setupOnce = function () {
            var _this = this;
            if (this._options.console) {
                addInstrumentationHandler({
                    callback: function () {
                        var args = [];
                        for (var _i = 0; _i < arguments.length; _i++) {
                            args[_i] = arguments[_i];
                        }
                        _this._consoleBreadcrumb.apply(_this, __spread(args));
                    },
                    type: 'console',
                });
            }
            if (this._options.dom) {
                addInstrumentationHandler({
                    callback: function () {
                        var args = [];
                        for (var _i = 0; _i < arguments.length; _i++) {
                            args[_i] = arguments[_i];
                        }
                        _this._domBreadcrumb.apply(_this, __spread(args));
                    },
                    type: 'dom',
                });
            }
            if (this._options.xhr) {
                addInstrumentationHandler({
                    callback: function () {
                        var args = [];
                        for (var _i = 0; _i < arguments.length; _i++) {
                            args[_i] = arguments[_i];
                        }
                        _this._xhrBreadcrumb.apply(_this, __spread(args));
                    },
                    type: 'xhr',
                });
            }
            if (this._options.fetch) {
                addInstrumentationHandler({
                    callback: function () {
                        var args = [];
                        for (var _i = 0; _i < arguments.length; _i++) {
                            args[_i] = arguments[_i];
                        }
                        _this._fetchBreadcrumb.apply(_this, __spread(args));
                    },
                    type: 'fetch',
                });
            }
            if (this._options.history) {
                addInstrumentationHandler({
                    callback: function () {
                        var args = [];
                        for (var _i = 0; _i < arguments.length; _i++) {
                            args[_i] = arguments[_i];
                        }
                        _this._historyBreadcrumb.apply(_this, __spread(args));
                    },
                    type: 'history',
                });
            }
        };
        /**
         * Creates breadcrumbs from console API calls
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Breadcrumbs.prototype._consoleBreadcrumb = function (handlerData) {
            var breadcrumb = {
                category: 'console',
                data: {
                    arguments: handlerData.args,
                    logger: 'console',
                },
                level: exports.Severity.fromString(handlerData.level),
                message: safeJoin(handlerData.args, ' '),
            };
            if (handlerData.level === 'assert') {
                if (handlerData.args[0] === false) {
                    breadcrumb.message = "Assertion failed: " + (safeJoin(handlerData.args.slice(1), ' ') || 'console.assert');
                    breadcrumb.data.arguments = handlerData.args.slice(1);
                }
                else {
                    // Don't capture a breadcrumb for passed assertions
                    return;
                }
            }
            getCurrentHub().addBreadcrumb(breadcrumb, {
                input: handlerData.args,
                level: handlerData.level,
            });
        };
        /**
         * Creates breadcrumbs from DOM API calls
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Breadcrumbs.prototype._domBreadcrumb = function (handlerData) {
            var target;
            var keyAttrs = typeof this._options.dom === 'object' ? this._options.dom.serializeAttribute : undefined;
            if (typeof keyAttrs === 'string') {
                keyAttrs = [keyAttrs];
            }
            // Accessing event.target can throw (see getsentry/raven-js#838, #768)
            try {
                target = handlerData.event.target
                    ? htmlTreeAsString(handlerData.event.target, keyAttrs)
                    : htmlTreeAsString(handlerData.event, keyAttrs);
            }
            catch (e) {
                target = '<unknown>';
            }
            if (target.length === 0) {
                return;
            }
            getCurrentHub().addBreadcrumb({
                category: "ui." + handlerData.name,
                message: target,
            }, {
                event: handlerData.event,
                name: handlerData.name,
                global: handlerData.global,
            });
        };
        /**
         * Creates breadcrumbs from XHR API calls
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Breadcrumbs.prototype._xhrBreadcrumb = function (handlerData) {
            if (handlerData.endTimestamp) {
                // We only capture complete, non-sentry requests
                if (handlerData.xhr.__sentry_own_request__) {
                    return;
                }
                var _a = handlerData.xhr.__sentry_xhr__ || {}, method = _a.method, url = _a.url, status_code = _a.status_code, body = _a.body;
                getCurrentHub().addBreadcrumb({
                    category: 'xhr',
                    data: {
                        method: method,
                        url: url,
                        status_code: status_code,
                    },
                    type: 'http',
                }, {
                    xhr: handlerData.xhr,
                    input: body,
                });
                return;
            }
        };
        /**
         * Creates breadcrumbs from fetch API calls
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Breadcrumbs.prototype._fetchBreadcrumb = function (handlerData) {
            // We only capture complete fetch requests
            if (!handlerData.endTimestamp) {
                return;
            }
            if (handlerData.fetchData.url.match(/sentry_key/) && handlerData.fetchData.method === 'POST') {
                // We will not create breadcrumbs for fetch requests that contain `sentry_key` (internal sentry requests)
                return;
            }
            if (handlerData.error) {
                getCurrentHub().addBreadcrumb({
                    category: 'fetch',
                    data: handlerData.fetchData,
                    level: exports.Severity.Error,
                    type: 'http',
                }, {
                    data: handlerData.error,
                    input: handlerData.args,
                });
            }
            else {
                getCurrentHub().addBreadcrumb({
                    category: 'fetch',
                    data: __assign(__assign({}, handlerData.fetchData), { status_code: handlerData.response.status }),
                    type: 'http',
                }, {
                    input: handlerData.args,
                    response: handlerData.response,
                });
            }
        };
        /**
         * Creates breadcrumbs from history API calls
         */
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Breadcrumbs.prototype._historyBreadcrumb = function (handlerData) {
            var global = getGlobalObject();
            var from = handlerData.from;
            var to = handlerData.to;
            var parsedLoc = parseUrl(global.location.href);
            var parsedFrom = parseUrl(from);
            var parsedTo = parseUrl(to);
            // Initial pushState doesn't provide `from` information
            if (!parsedFrom.path) {
                parsedFrom = parsedLoc;
            }
            // Use only the path component of the URL if the URL matches the current
            // document (almost all the time when using pushState)
            if (parsedLoc.protocol === parsedTo.protocol && parsedLoc.host === parsedTo.host) {
                to = parsedTo.relative;
            }
            if (parsedLoc.protocol === parsedFrom.protocol && parsedLoc.host === parsedFrom.host) {
                from = parsedFrom.relative;
            }
            getCurrentHub().addBreadcrumb({
                category: 'navigation',
                data: {
                    from: from,
                    to: to,
                },
            });
        };
        /**
         * @inheritDoc
         */
        Breadcrumbs.id = 'Breadcrumbs';
        return Breadcrumbs;
    }());

    var DEFAULT_KEY = 'cause';
    var DEFAULT_LIMIT = 5;
    /** Adds SDK info to an event. */
    var LinkedErrors = /** @class */ (function () {
        /**
         * @inheritDoc
         */
        function LinkedErrors(options) {
            if (options === void 0) { options = {}; }
            /**
             * @inheritDoc
             */
            this.name = LinkedErrors.id;
            this._key = options.key || DEFAULT_KEY;
            this._limit = options.limit || DEFAULT_LIMIT;
        }
        /**
         * @inheritDoc
         */
        LinkedErrors.prototype.setupOnce = function () {
            addGlobalEventProcessor(function (event, hint) {
                var self = getCurrentHub().getIntegration(LinkedErrors);
                if (self) {
                    var handler = self._handler && self._handler.bind(self);
                    return typeof handler === 'function' ? handler(event, hint) : event;
                }
                return event;
            });
        };
        /**
         * @inheritDoc
         */
        LinkedErrors.prototype._handler = function (event, hint) {
            if (!event.exception || !event.exception.values || !hint || !isInstanceOf(hint.originalException, Error)) {
                return event;
            }
            var linkedErrors = this._walkErrorTree(hint.originalException, this._key);
            event.exception.values = __spread(linkedErrors, event.exception.values);
            return event;
        };
        /**
         * @inheritDoc
         */
        LinkedErrors.prototype._walkErrorTree = function (error, key, stack) {
            if (stack === void 0) { stack = []; }
            if (!isInstanceOf(error[key], Error) || stack.length + 1 >= this._limit) {
                return stack;
            }
            var stacktrace = computeStackTrace(error[key]);
            var exception = exceptionFromStacktrace(stacktrace);
            return this._walkErrorTree(error[key], key, __spread([exception], stack));
        };
        /**
         * @inheritDoc
         */
        LinkedErrors.id = 'LinkedErrors';
        return LinkedErrors;
    }());

    var global$3 = getGlobalObject();
    /** UserAgent */
    var UserAgent = /** @class */ (function () {
        function UserAgent() {
            /**
             * @inheritDoc
             */
            this.name = UserAgent.id;
        }
        /**
         * @inheritDoc
         */
        UserAgent.prototype.setupOnce = function () {
            addGlobalEventProcessor(function (event) {
                var _a, _b, _c;
                if (getCurrentHub().getIntegration(UserAgent)) {
                    // if none of the information we want exists, don't bother
                    if (!global$3.navigator && !global$3.location && !global$3.document) {
                        return event;
                    }
                    // grab as much info as exists and add it to the event
                    var url = ((_a = event.request) === null || _a === void 0 ? void 0 : _a.url) || ((_b = global$3.location) === null || _b === void 0 ? void 0 : _b.href);
                    var referrer = (global$3.document || {}).referrer;
                    var userAgent = (global$3.navigator || {}).userAgent;
                    var headers = __assign(__assign(__assign({}, (_c = event.request) === null || _c === void 0 ? void 0 : _c.headers), (referrer && { Referer: referrer })), (userAgent && { 'User-Agent': userAgent }));
                    var request = __assign(__assign({}, (url && { url: url })), { headers: headers });
                    return __assign(__assign({}, event), { request: request });
                }
                return event;
            });
        };
        /**
         * @inheritDoc
         */
        UserAgent.id = 'UserAgent';
        return UserAgent;
    }());

    /** Deduplication filter */
    var Dedupe = /** @class */ (function () {
        function Dedupe() {
            /**
             * @inheritDoc
             */
            this.name = Dedupe.id;
        }
        /**
         * @inheritDoc
         */
        Dedupe.prototype.setupOnce = function (addGlobalEventProcessor, getCurrentHub) {
            addGlobalEventProcessor(function (currentEvent) {
                var self = getCurrentHub().getIntegration(Dedupe);
                if (self) {
                    // Juuust in case something goes wrong
                    try {
                        if (self._shouldDropEvent(currentEvent, self._previousEvent)) {
                            return null;
                        }
                    }
                    catch (_oO) {
                        return (self._previousEvent = currentEvent);
                    }
                    return (self._previousEvent = currentEvent);
                }
                return currentEvent;
            });
        };
        /** JSDoc */
        Dedupe.prototype._shouldDropEvent = function (currentEvent, previousEvent) {
            if (!previousEvent) {
                return false;
            }
            if (this._isSameMessageEvent(currentEvent, previousEvent)) {
                return true;
            }
            if (this._isSameExceptionEvent(currentEvent, previousEvent)) {
                return true;
            }
            return false;
        };
        /** JSDoc */
        Dedupe.prototype._isSameMessageEvent = function (currentEvent, previousEvent) {
            var currentMessage = currentEvent.message;
            var previousMessage = previousEvent.message;
            // If neither event has a message property, they were both exceptions, so bail out
            if (!currentMessage && !previousMessage) {
                return false;
            }
            // If only one event has a stacktrace, but not the other one, they are not the same
            if ((currentMessage && !previousMessage) || (!currentMessage && previousMessage)) {
                return false;
            }
            if (currentMessage !== previousMessage) {
                return false;
            }
            if (!this._isSameFingerprint(currentEvent, previousEvent)) {
                return false;
            }
            if (!this._isSameStacktrace(currentEvent, previousEvent)) {
                return false;
            }
            return true;
        };
        /** JSDoc */
        Dedupe.prototype._getFramesFromEvent = function (event) {
            var exception = event.exception;
            if (exception) {
                try {
                    // @ts-ignore Object could be undefined
                    return exception.values[0].stacktrace.frames;
                }
                catch (_oO) {
                    return undefined;
                }
            }
            else if (event.stacktrace) {
                return event.stacktrace.frames;
            }
            return undefined;
        };
        /** JSDoc */
        Dedupe.prototype._isSameStacktrace = function (currentEvent, previousEvent) {
            var currentFrames = this._getFramesFromEvent(currentEvent);
            var previousFrames = this._getFramesFromEvent(previousEvent);
            // If neither event has a stacktrace, they are assumed to be the same
            if (!currentFrames && !previousFrames) {
                return true;
            }
            // If only one event has a stacktrace, but not the other one, they are not the same
            if ((currentFrames && !previousFrames) || (!currentFrames && previousFrames)) {
                return false;
            }
            currentFrames = currentFrames;
            previousFrames = previousFrames;
            // If number of frames differ, they are not the same
            if (previousFrames.length !== currentFrames.length) {
                return false;
            }
            // Otherwise, compare the two
            for (var i = 0; i < previousFrames.length; i++) {
                var frameA = previousFrames[i];
                var frameB = currentFrames[i];
                if (frameA.filename !== frameB.filename ||
                    frameA.lineno !== frameB.lineno ||
                    frameA.colno !== frameB.colno ||
                    frameA.function !== frameB.function) {
                    return false;
                }
            }
            return true;
        };
        /** JSDoc */
        Dedupe.prototype._getExceptionFromEvent = function (event) {
            return event.exception && event.exception.values && event.exception.values[0];
        };
        /** JSDoc */
        Dedupe.prototype._isSameExceptionEvent = function (currentEvent, previousEvent) {
            var previousException = this._getExceptionFromEvent(previousEvent);
            var currentException = this._getExceptionFromEvent(currentEvent);
            if (!previousException || !currentException) {
                return false;
            }
            if (previousException.type !== currentException.type || previousException.value !== currentException.value) {
                return false;
            }
            if (!this._isSameFingerprint(currentEvent, previousEvent)) {
                return false;
            }
            if (!this._isSameStacktrace(currentEvent, previousEvent)) {
                return false;
            }
            return true;
        };
        /** JSDoc */
        Dedupe.prototype._isSameFingerprint = function (currentEvent, previousEvent) {
            var currentFingerprint = currentEvent.fingerprint;
            var previousFingerprint = previousEvent.fingerprint;
            // If neither event has a fingerprint, they are assumed to be the same
            if (!currentFingerprint && !previousFingerprint) {
                return true;
            }
            // If only one event has a fingerprint, but not the other one, they are not the same
            if ((currentFingerprint && !previousFingerprint) || (!currentFingerprint && previousFingerprint)) {
                return false;
            }
            currentFingerprint = currentFingerprint;
            previousFingerprint = previousFingerprint;
            // Otherwise, compare the two
            try {
                return !!(currentFingerprint.join('') === previousFingerprint.join(''));
            }
            catch (_oO) {
                return false;
            }
        };
        /**
         * @inheritDoc
         */
        Dedupe.id = 'Dedupe';
        return Dedupe;
    }());



    var BrowserIntegrations = /*#__PURE__*/Object.freeze({
        __proto__: null,
        GlobalHandlers: GlobalHandlers,
        TryCatch: TryCatch,
        Breadcrumbs: Breadcrumbs,
        LinkedErrors: LinkedErrors,
        UserAgent: UserAgent,
        Dedupe: Dedupe
    });

    /**
     * The Sentry Browser SDK Client.
     *
     * @see BrowserOptions for documentation on configuration options.
     * @see SentryClient for usage documentation.
     */
    var BrowserClient = /** @class */ (function (_super) {
        __extends(BrowserClient, _super);
        /**
         * Creates a new Browser SDK instance.
         *
         * @param options Configuration options for this SDK.
         */
        function BrowserClient(options) {
            if (options === void 0) { options = {}; }
            var _this = this;
            options._metadata = options._metadata || {};
            options._metadata.sdk = options._metadata.sdk || {
                name: 'sentry.javascript.browser',
                packages: [
                    {
                        name: 'npm:@sentry/browser',
                        version: SDK_VERSION,
                    },
                ],
                version: SDK_VERSION,
            };
            _this = _super.call(this, BrowserBackend, options) || this;
            return _this;
        }
        /**
         * Show a report dialog to the user to send feedback to a specific event.
         *
         * @param options Set individual options for the dialog
         */
        BrowserClient.prototype.showReportDialog = function (options) {
            if (options === void 0) { options = {}; }
            // doesn't work without a document (React Native)
            var document = getGlobalObject().document;
            if (!document) {
                return;
            }
            if (!this._isEnabled()) {
                logger.error('Trying to call showReportDialog with Sentry Client disabled');
                return;
            }
            injectReportDialog(__assign(__assign({}, options), { dsn: options.dsn || this.getDsn() }));
        };
        /**
         * @inheritDoc
         */
        BrowserClient.prototype._prepareEvent = function (event, scope, hint) {
            event.platform = event.platform || 'javascript';
            return _super.prototype._prepareEvent.call(this, event, scope, hint);
        };
        /**
         * @inheritDoc
         */
        BrowserClient.prototype._sendEvent = function (event) {
            var integration = this.getIntegration(Breadcrumbs);
            if (integration) {
                integration.addSentryBreadcrumb(event);
            }
            _super.prototype._sendEvent.call(this, event);
        };
        return BrowserClient;
    }(BaseClient));

    var defaultIntegrations = [
        new InboundFilters(),
        new FunctionToString(),
        new TryCatch(),
        new Breadcrumbs(),
        new GlobalHandlers(),
        new LinkedErrors(),
        new Dedupe(),
        new UserAgent(),
    ];
    /**
     * The Sentry Browser SDK Client.
     *
     * To use this SDK, call the {@link init} function as early as possible when
     * loading the web page. To set context information or send manual events, use
     * the provided methods.
     *
     * @example
     *
     * ```
     *
     * import { init } from '@sentry/browser';
     *
     * init({
     *   dsn: '__DSN__',
     *   // ...
     * });
     * ```
     *
     * @example
     * ```
     *
     * import { configureScope } from '@sentry/browser';
     * configureScope((scope: Scope) => {
     *   scope.setExtra({ battery: 0.7 });
     *   scope.setTag({ user_mode: 'admin' });
     *   scope.setUser({ id: '4711' });
     * });
     * ```
     *
     * @example
     * ```
     *
     * import { addBreadcrumb } from '@sentry/browser';
     * addBreadcrumb({
     *   message: 'My Breadcrumb',
     *   // ...
     * });
     * ```
     *
     * @example
     *
     * ```
     *
     * import * as Sentry from '@sentry/browser';
     * Sentry.captureMessage('Hello, world!');
     * Sentry.captureException(new Error('Good bye'));
     * Sentry.captureEvent({
     *   message: 'Manual',
     *   stacktrace: [
     *     // ...
     *   ],
     * });
     * ```
     *
     * @see {@link BrowserOptions} for documentation on configuration options.
     */
    function init(options) {
        if (options === void 0) { options = {}; }
        if (options.defaultIntegrations === undefined) {
            options.defaultIntegrations = defaultIntegrations;
        }
        if (options.release === undefined) {
            var window_1 = getGlobalObject();
            // This supports the variable that sentry-webpack-plugin injects
            if (window_1.SENTRY_RELEASE && window_1.SENTRY_RELEASE.id) {
                options.release = window_1.SENTRY_RELEASE.id;
            }
        }
        if (options.autoSessionTracking === undefined) {
            options.autoSessionTracking = true;
        }
        initAndBind(BrowserClient, options);
        if (options.autoSessionTracking) {
            startSessionTracking();
        }
    }
    /**
     * Present the user with a report dialog.
     *
     * @param options Everything is optional, we try to fetch all info need from the global scope.
     */
    function showReportDialog(options) {
        if (options === void 0) { options = {}; }
        var hub = getCurrentHub();
        var scope = hub.getScope();
        if (scope) {
            options.user = __assign(__assign({}, scope.getUser()), options.user);
        }
        if (!options.eventId) {
            options.eventId = hub.lastEventId();
        }
        var client = hub.getClient();
        if (client) {
            client.showReportDialog(options);
        }
    }
    /**
     * This is the getter for lastEventId.
     *
     * @returns The last event id of a captured event.
     */
    function lastEventId() {
        return getCurrentHub().lastEventId();
    }
    /**
     * This function is here to be API compatible with the loader.
     * @hidden
     */
    function forceLoad() {
        // Noop
    }
    /**
     * This function is here to be API compatible with the loader.
     * @hidden
     */
    function onLoad(callback) {
        callback();
    }
    /**
     * Call `flush()` on the current client, if there is one. See {@link Client.flush}.
     *
     * @param timeout Maximum time in ms the client should wait to flush its event queue. Omitting this parameter will cause
     * the client to wait until all events are sent before resolving the promise.
     * @returns A promise which resolves to `true` if the queue successfully drains before the timeout, or `false` if it
     * doesn't (or if there's no client defined).
     */
    function flush(timeout) {
        var client = getCurrentHub().getClient();
        if (client) {
            return client.flush(timeout);
        }
        logger.warn('Cannot flush events. No client defined.');
        return SyncPromise.resolve(false);
    }
    /**
     * Call `close()` on the current client, if there is one. See {@link Client.close}.
     *
     * @param timeout Maximum time in ms the client should wait to flush its event queue before shutting down. Omitting this
     * parameter will cause the client to wait until all events are sent before disabling itself.
     * @returns A promise which resolves to `true` if the queue successfully drains before the timeout, or `false` if it
     * doesn't (or if there's no client defined).
     */
    function close(timeout) {
        var client = getCurrentHub().getClient();
        if (client) {
            return client.close(timeout);
        }
        logger.warn('Cannot flush events and disable SDK. No client defined.');
        return SyncPromise.resolve(false);
    }
    /**
     * Wrap code within a try/catch block so the SDK is able to capture errors.
     *
     * @param fn A function to wrap.
     *
     * @returns The result of wrapped function call.
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    function wrap$1(fn) {
        return wrap(fn)();
    }
    /**
     * Enable automatic Session Tracking for the initial page load.
     */
    function startSessionTracking() {
        var window = getGlobalObject();
        var document = window.document;
        if (typeof document === 'undefined') {
            logger.warn('Session tracking in non-browser environment with @sentry/browser is not supported.');
            return;
        }
        var hub = getCurrentHub();
        // The only way for this to be false is for there to be a version mismatch between @sentry/browser (>= 6.0.0) and
        // @sentry/hub (< 5.27.0). In the simple case, there won't ever be such a mismatch, because the two packages are
        // pinned at the same version in package.json, but there are edge cases where it's possible. See
        // https://github.com/getsentry/sentry-javascript/issues/3207 and
        // https://github.com/getsentry/sentry-javascript/issues/3234 and
        // https://github.com/getsentry/sentry-javascript/issues/3278.
        if (typeof hub.startSession !== 'function' || typeof hub.captureSession !== 'function') {
            return;
        }
        // The session duration for browser sessions does not track a meaningful
        // concept that can be used as a metric.
        // Automatically captured sessions are akin to page views, and thus we
        // discard their duration.
        hub.startSession({ ignoreDuration: true });
        hub.captureSession();
        // We want to create a session for every navigation as well
        addInstrumentationHandler({
            callback: function (_a) {
                var from = _a.from, to = _a.to;
                // Don't create an additional session for the initial route or if the location did not change
                if (from === undefined || from === to) {
                    return;
                }
                hub.startSession({ ignoreDuration: true });
                hub.captureSession();
            },
            type: 'history',
        });
    }

    // TODO: Remove in the next major release and rely only on @sentry/core SDK_VERSION and SdkInfo metadata
    var SDK_NAME = 'sentry.javascript.browser';

    var windowIntegrations = {};
    // This block is needed to add compatibility with the integrations packages when used with a CDN
    var _window = getGlobalObject();
    if (_window.Sentry && _window.Sentry.Integrations) {
        windowIntegrations = _window.Sentry.Integrations;
    }
    var INTEGRATIONS = __assign(__assign(__assign({}, windowIntegrations), CoreIntegrations), BrowserIntegrations);

    exports.BrowserClient = BrowserClient;
    exports.Hub = Hub;
    exports.Integrations = INTEGRATIONS;
    exports.SDK_NAME = SDK_NAME;
    exports.SDK_VERSION = SDK_VERSION;
    exports.Scope = Scope;
    exports.Transports = index;
    exports.addBreadcrumb = addBreadcrumb;
    exports.addGlobalEventProcessor = addGlobalEventProcessor;
    exports.captureEvent = captureEvent;
    exports.captureException = captureException;
    exports.captureMessage = captureMessage;
    exports.close = close;
    exports.configureScope = configureScope;
    exports.defaultIntegrations = defaultIntegrations;
    exports.eventFromException = eventFromException;
    exports.eventFromMessage = eventFromMessage;
    exports.flush = flush;
    exports.forceLoad = forceLoad;
    exports.getCurrentHub = getCurrentHub;
    exports.getHubFromCarrier = getHubFromCarrier;
    exports.init = init;
    exports.injectReportDialog = injectReportDialog;
    exports.lastEventId = lastEventId;
    exports.makeMain = makeMain;
    exports.onLoad = onLoad;
    exports.setContext = setContext;
    exports.setExtra = setExtra;
    exports.setExtras = setExtras;
    exports.setTag = setTag;
    exports.setTags = setTags;
    exports.setUser = setUser;
    exports.showReportDialog = showReportDialog;
    exports.startTransaction = startTransaction;
    exports.withScope = withScope;
    exports.wrap = wrap$1;

    return exports;

}({}));
//# sourceMappingURL=bundle.js.map
