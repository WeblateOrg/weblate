(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}else if(typeof define==="function"&&define.amd){define([],f)}else{var g;if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}else if(typeof self!=="undefined"){g=self}else{g=this}g.Sentry = f()}})(function(){var define,module,exports;return (function(){function r(e,n,t){function o(i,f){if(!n[i]){if(!e[i]){var c="function"==typeof require&&require;if(!f&&c)return c(i,!0);if(u)return u(i,!0);var a=new Error("Cannot find module '"+i+"'");throw a.code="MODULE_NOT_FOUND",a}var p=n[i]={exports:{}};e[i][0].call(p.exports,function(r){var n=e[i][1][r];return o(n||r)},p,p.exports,r,e,n,t)}return n[i].exports}for(var u="function"==typeof require&&require,i=0;i<t.length;i++)o(t[i]);return o}return r})()({1:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const eventbuilder = require('./eventbuilder.js');
const helpers = require('./helpers.js');
const breadcrumbs = require('./integrations/breadcrumbs.js');

/**
 * Configuration options for the Sentry Browser SDK.
 * @see @sentry/types Options for more information.
 */

/**
 * The Sentry Browser SDK Client.
 *
 * @see BrowserOptions for documentation on configuration options.
 * @see SentryClient for usage documentation.
 */
class BrowserClient extends core.BaseClient {
  /**
   * Creates a new Browser SDK instance.
   *
   * @param options Configuration options for this SDK.
   */
   constructor(options) {
    options._metadata = options._metadata || {};
    options._metadata.sdk = options._metadata.sdk || {
      name: 'sentry.javascript.browser',
      packages: [
        {
          name: 'npm:@sentry/browser',
          version: core.SDK_VERSION,
        },
      ],
      version: core.SDK_VERSION,
    };

    super(options);

    if (options.sendClientReports && helpers.WINDOW.document) {
      helpers.WINDOW.document.addEventListener('visibilitychange', () => {
        if (helpers.WINDOW.document.visibilityState === 'hidden') {
          this._flushOutcomes();
        }
      });
    }
  }

  /**
   * @inheritDoc
   */
   eventFromException(exception, hint) {
    return eventbuilder.eventFromException(this._options.stackParser, exception, hint, this._options.attachStacktrace);
  }

  /**
   * @inheritDoc
   */
   eventFromMessage(
    message,
    // eslint-disable-next-line deprecation/deprecation
    level = 'info',
    hint,
  ) {
    return eventbuilder.eventFromMessage(this._options.stackParser, message, level, hint, this._options.attachStacktrace);
  }

  /**
   * @inheritDoc
   */
   sendEvent(event, hint) {
    // We only want to add the sentry event breadcrumb when the user has the breadcrumb integration installed and
    // activated its `sentry` option.
    // We also do not want to use the `Breadcrumbs` class here directly, because we do not want it to be included in
    // bundles, if it is not used by the SDK.
    // This all sadly is a bit ugly, but we currently don't have a "pre-send" hook on the integrations so we do it this
    // way for now.
    const breadcrumbIntegration = this.getIntegrationById(breadcrumbs.BREADCRUMB_INTEGRATION_ID) ;
    // We check for definedness of `addSentryBreadcrumb` in case users provided their own integration with id
    // "Breadcrumbs" that does not have this function.
    _optionalChain([breadcrumbIntegration, 'optionalAccess', _ => _.addSentryBreadcrumb, 'optionalCall', _2 => _2(event)]);

    super.sendEvent(event, hint);
  }

  /**
   * @inheritDoc
   */
   _prepareEvent(event, hint, scope) {
    event.platform = event.platform || 'javascript';
    return super._prepareEvent(event, hint, scope);
  }

  /**
   * Sends client reports as an envelope.
   */
   _flushOutcomes() {
    const outcomes = this._clearOutcomes();

    if (outcomes.length === 0) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('No outcomes to send');
      return;
    }

    if (!this._dsn) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('No dsn provided, will not send outcomes');
      return;
    }

    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('Sending outcomes:', outcomes);

    const url = core.getEnvelopeEndpointWithUrlEncodedAuth(this._dsn, this._options);
    const envelope = utils.createClientReportEnvelope(outcomes, this._options.tunnel && utils.dsnToString(this._dsn));

    try {
      const isRealNavigator = Object.prototype.toString.call(helpers.WINDOW && helpers.WINDOW.navigator) === '[object Navigator]';
      const hasSendBeacon = isRealNavigator && typeof helpers.WINDOW.navigator.sendBeacon === 'function';
      // Make sure beacon is not used if user configures custom transport options
      if (hasSendBeacon && !this._options.transportOptions) {
        // Prevent illegal invocations - https://xgwang.me/posts/you-may-not-know-beacon/#it-may-throw-error%2C-be-sure-to-catch
        const sendBeacon = helpers.WINDOW.navigator.sendBeacon.bind(helpers.WINDOW.navigator);
        sendBeacon(url, utils.serializeEnvelope(envelope));
      } else {
        // If beacon is not supported or if they are using the tunnel option
        // use our regular transport to send client reports to Sentry.
        this._sendEnvelope(envelope);
      }
    } catch (e) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error(e);
    }
  }
}

exports.BrowserClient = BrowserClient;


},{"./eventbuilder.js":2,"./helpers.js":4,"./integrations/breadcrumbs.js":6,"@sentry/core":24,"@sentry/utils":130,"@sentry/utils/cjs/buildPolyfills":124}],2:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');

/**
 * This function creates an exception from a JavaScript Error
 */
function exceptionFromError(stackParser, ex) {
  // Get the frames first since Opera can lose the stack if we touch anything else first
  const frames = parseStackFrames(stackParser, ex);

  const exception = {
    type: ex && ex.name,
    value: extractMessage(ex),
  };

  if (frames.length) {
    exception.stacktrace = { frames };
  }

  if (exception.type === undefined && exception.value === '') {
    exception.value = 'Unrecoverable error caught';
  }

  return exception;
}

/**
 * @hidden
 */
function eventFromPlainObject(
  stackParser,
  exception,
  syntheticException,
  isUnhandledRejection,
) {
  const hub = core.getCurrentHub();
  const client = hub.getClient();
  const normalizeDepth = client && client.getOptions().normalizeDepth;

  const event = {
    exception: {
      values: [
        {
          type: utils.isEvent(exception) ? exception.constructor.name : isUnhandledRejection ? 'UnhandledRejection' : 'Error',
          value: `Non-Error ${
            isUnhandledRejection ? 'promise rejection' : 'exception'
          } captured with keys: ${utils.extractExceptionKeysForMessage(exception)}`,
        },
      ],
    },
    extra: {
      __serialized__: utils.normalizeToSize(exception, normalizeDepth),
    },
  };

  if (syntheticException) {
    const frames = parseStackFrames(stackParser, syntheticException);
    if (frames.length) {
      // event.exception.values[0] has been set above
      (event.exception ).values[0].stacktrace = { frames };
    }
  }

  return event;
}

/**
 * @hidden
 */
function eventFromError(stackParser, ex) {
  return {
    exception: {
      values: [exceptionFromError(stackParser, ex)],
    },
  };
}

/** Parses stack frames from an error */
function parseStackFrames(
  stackParser,
  ex,
) {
  // Access and store the stacktrace property before doing ANYTHING
  // else to it because Opera is not very good at providing it
  // reliably in other circumstances.
  const stacktrace = ex.stacktrace || ex.stack || '';

  const popSize = getPopSize(ex);

  try {
    return stackParser(stacktrace, popSize);
  } catch (e) {
    // no-empty
  }

  return [];
}

// Based on our own mapping pattern - https://github.com/getsentry/sentry/blob/9f08305e09866c8bd6d0c24f5b0aabdd7dd6c59c/src/sentry/lang/javascript/errormapping.py#L83-L108
const reactMinifiedRegexp = /Minified React error #\d+;/i;

function getPopSize(ex) {
  if (ex) {
    if (typeof ex.framesToPop === 'number') {
      return ex.framesToPop;
    }

    if (reactMinifiedRegexp.test(ex.message)) {
      return 1;
    }
  }

  return 0;
}

/**
 * There are cases where stacktrace.message is an Event object
 * https://github.com/getsentry/sentry-javascript/issues/1949
 * In this specific case we try to extract stacktrace.message.error.message
 */
function extractMessage(ex) {
  const message = ex && ex.message;
  if (!message) {
    return 'No error message';
  }
  if (message.error && typeof message.error.message === 'string') {
    return message.error.message;
  }
  return message;
}

/**
 * Creates an {@link Event} from all inputs to `captureException` and non-primitive inputs to `captureMessage`.
 * @hidden
 */
function eventFromException(
  stackParser,
  exception,
  hint,
  attachStacktrace,
) {
  const syntheticException = (hint && hint.syntheticException) || undefined;
  const event = eventFromUnknownInput(stackParser, exception, syntheticException, attachStacktrace);
  utils.addExceptionMechanism(event); // defaults to { type: 'generic', handled: true }
  event.level = 'error';
  if (hint && hint.event_id) {
    event.event_id = hint.event_id;
  }
  return utils.resolvedSyncPromise(event);
}

/**
 * Builds and Event from a Message
 * @hidden
 */
function eventFromMessage(
  stackParser,
  message,
  // eslint-disable-next-line deprecation/deprecation
  level = 'info',
  hint,
  attachStacktrace,
) {
  const syntheticException = (hint && hint.syntheticException) || undefined;
  const event = eventFromString(stackParser, message, syntheticException, attachStacktrace);
  event.level = level;
  if (hint && hint.event_id) {
    event.event_id = hint.event_id;
  }
  return utils.resolvedSyncPromise(event);
}

/**
 * @hidden
 */
function eventFromUnknownInput(
  stackParser,
  exception,
  syntheticException,
  attachStacktrace,
  isUnhandledRejection,
) {
  let event;

  if (utils.isErrorEvent(exception ) && (exception ).error) {
    // If it is an ErrorEvent with `error` property, extract it to get actual Error
    const errorEvent = exception ;
    return eventFromError(stackParser, errorEvent.error );
  }

  // If it is a `DOMError` (which is a legacy API, but still supported in some browsers) then we just extract the name
  // and message, as it doesn't provide anything else. According to the spec, all `DOMExceptions` should also be
  // `Error`s, but that's not the case in IE11, so in that case we treat it the same as we do a `DOMError`.
  //
  // https://developer.mozilla.org/en-US/docs/Web/API/DOMError
  // https://developer.mozilla.org/en-US/docs/Web/API/DOMException
  // https://webidl.spec.whatwg.org/#es-DOMException-specialness
  if (utils.isDOMError(exception ) || utils.isDOMException(exception )) {
    const domException = exception ;

    if ('stack' in (exception )) {
      event = eventFromError(stackParser, exception );
    } else {
      const name = domException.name || (utils.isDOMError(domException) ? 'DOMError' : 'DOMException');
      const message = domException.message ? `${name}: ${domException.message}` : name;
      event = eventFromString(stackParser, message, syntheticException, attachStacktrace);
      utils.addExceptionTypeValue(event, message);
    }
    if ('code' in domException) {
      event.tags = { ...event.tags, 'DOMException.code': `${domException.code}` };
    }

    return event;
  }
  if (utils.isError(exception)) {
    // we have a real Error object, do nothing
    return eventFromError(stackParser, exception);
  }
  if (utils.isPlainObject(exception) || utils.isEvent(exception)) {
    // If it's a plain object or an instance of `Event` (the built-in JS kind, not this SDK's `Event` type), serialize
    // it manually. This will allow us to group events based on top-level keys which is much better than creating a new
    // group on any key/value change.
    const objectException = exception ;
    event = eventFromPlainObject(stackParser, objectException, syntheticException, isUnhandledRejection);
    utils.addExceptionMechanism(event, {
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
  event = eventFromString(stackParser, exception , syntheticException, attachStacktrace);
  utils.addExceptionTypeValue(event, `${exception}`, undefined);
  utils.addExceptionMechanism(event, {
    synthetic: true,
  });

  return event;
}

/**
 * @hidden
 */
function eventFromString(
  stackParser,
  input,
  syntheticException,
  attachStacktrace,
) {
  const event = {
    message: input,
  };

  if (attachStacktrace && syntheticException) {
    const frames = parseStackFrames(stackParser, syntheticException);
    if (frames.length) {
      event.exception = {
        values: [{ value: input, stacktrace: { frames } }],
      };
    }
  }

  return event;
}

exports.eventFromError = eventFromError;
exports.eventFromException = eventFromException;
exports.eventFromMessage = eventFromMessage;
exports.eventFromPlainObject = eventFromPlainObject;
exports.eventFromString = eventFromString;
exports.eventFromUnknownInput = eventFromUnknownInput;
exports.exceptionFromError = exceptionFromError;
exports.parseStackFrames = parseStackFrames;


},{"@sentry/core":24,"@sentry/utils":130}],3:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const helpers = require('./helpers.js');
const client = require('./client.js');
require('./transports/index.js');
const stackParsers = require('./stack-parsers.js');
const eventbuilder = require('./eventbuilder.js');
const sdk = require('./sdk.js');
require('./integrations/index.js');

;

;
;

exports.FunctionToString = core.FunctionToString;
exports.Hub = core.Hub;
exports.InboundFilters = core.InboundFilters;
exports.SDK_VERSION = core.SDK_VERSION;
exports.Scope = core.Scope;
exports.addBreadcrumb = core.addBreadcrumb;
exports.addGlobalEventProcessor = core.addGlobalEventProcessor;
exports.captureEvent = core.captureEvent;
exports.captureException = core.captureException;
exports.captureMessage = core.captureMessage;
exports.configureScope = core.configureScope;
exports.createTransport = core.createTransport;
exports.getCurrentHub = core.getCurrentHub;
exports.getHubFromCarrier = core.getHubFromCarrier;
exports.makeMain = core.makeMain;
exports.setContext = core.setContext;
exports.setExtra = core.setExtra;
exports.setExtras = core.setExtras;
exports.setTag = core.setTag;
exports.setTags = core.setTags;
exports.setUser = core.setUser;
exports.startTransaction = core.startTransaction;
exports.withScope = core.withScope;
exports.WINDOW = helpers.WINDOW;
exports.BrowserClient = client.BrowserClient;
exports.chromeStackLineParser = stackParsers.chromeStackLineParser;
exports.defaultStackLineParsers = stackParsers.defaultStackLineParsers;
exports.defaultStackParser = stackParsers.defaultStackParser;
exports.geckoStackLineParser = stackParsers.geckoStackLineParser;
exports.opera10StackLineParser = stackParsers.opera10StackLineParser;
exports.opera11StackLineParser = stackParsers.opera11StackLineParser;
exports.winjsStackLineParser = stackParsers.winjsStackLineParser;
exports.eventFromException = eventbuilder.eventFromException;
exports.eventFromMessage = eventbuilder.eventFromMessage;
exports.close = sdk.close;
exports.defaultIntegrations = sdk.defaultIntegrations;
exports.flush = sdk.flush;
exports.forceLoad = sdk.forceLoad;
exports.init = sdk.init;
exports.lastEventId = sdk.lastEventId;
exports.onLoad = sdk.onLoad;
exports.showReportDialog = sdk.showReportDialog;
exports.wrap = sdk.wrap;


},{"./client.js":1,"./eventbuilder.js":2,"./helpers.js":4,"./integrations/index.js":10,"./sdk.js":13,"./stack-parsers.js":14,"./transports/index.js":16,"@sentry/core":24}],4:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');

const WINDOW = utils.GLOBAL_OBJ ;

let ignoreOnError = 0;

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
  ignoreOnError++;
  setTimeout(() => {
    ignoreOnError--;
  });
}

/**
 * Instruments the given function and sends an event to Sentry every time the
 * function throws an exception.
 *
 * @param fn A function to wrap. It is generally safe to pass an unbound function, because the returned wrapper always
 * has a correct `this` context.
 * @returns The wrapped function.
 * @hidden
 */
function wrap(
  fn,
  options

 = {},
  before,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
) {
  // for future readers what this does is wrap a function and then create
  // a bi-directional wrapping between them.
  //
  // example: wrapped = wrap(original);
  //  original.__sentry_wrapped__ -> wrapped
  //  wrapped.__sentry_original__ -> original

  if (typeof fn !== 'function') {
    return fn;
  }

  try {
    // if we're dealing with a function that was previously wrapped, return
    // the original wrapper.
    const wrapper = fn.__sentry_wrapped__;
    if (wrapper) {
      return wrapper;
    }

    // We don't wanna wrap it twice
    if (utils.getOriginalFunction(fn)) {
      return fn;
    }
  } catch (e) {
    // Just accessing custom props in some Selenium environments
    // can cause a "Permission denied" exception (see raven-js#495).
    // Bail on wrapping and return the function as-is (defers to window.onerror).
    return fn;
  }

  /* eslint-disable prefer-rest-params */
  // It is important that `sentryWrapped` is not an arrow function to preserve the context of `this`
  const sentryWrapped = function () {
    const args = Array.prototype.slice.call(arguments);

    try {
      if (before && typeof before === 'function') {
        before.apply(this, arguments);
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access
      const wrappedArguments = args.map((arg) => wrap(arg, options));

      // Attempt to invoke user-land function
      // NOTE: If you are a Sentry user, and you are seeing this stack frame, it
      //       means the sentry.javascript SDK caught an error invoking your application code. This
      //       is expected behavior and NOT indicative of a bug with sentry.javascript.
      return fn.apply(this, wrappedArguments);
    } catch (ex) {
      ignoreNextOnError();

      core.withScope((scope) => {
        scope.addEventProcessor((event) => {
          if (options.mechanism) {
            utils.addExceptionTypeValue(event, undefined, undefined);
            utils.addExceptionMechanism(event, options.mechanism);
          }

          event.extra = {
            ...event.extra,
            arguments: args,
          };

          return event;
        });

        core.captureException(ex);
      });

      throw ex;
    }
  };
  /* eslint-enable prefer-rest-params */

  // Accessing some objects may throw
  // ref: https://github.com/getsentry/sentry-javascript/issues/1168
  try {
    for (const property in fn) {
      if (Object.prototype.hasOwnProperty.call(fn, property)) {
        sentryWrapped[property] = fn[property];
      }
    }
  } catch (_oO) {} // eslint-disable-line no-empty

  // Signal that this function has been wrapped/filled already
  // for both debugging and to prevent it to being wrapped/filled twice
  utils.markFunctionWrapped(sentryWrapped, fn);

  utils.addNonEnumerableProperty(fn, '__sentry_wrapped__', sentryWrapped);

  // Restore original function name (not all browsers allow that)
  try {
    const descriptor = Object.getOwnPropertyDescriptor(sentryWrapped, 'name') ;
    if (descriptor.configurable) {
      Object.defineProperty(sentryWrapped, 'name', {
        get() {
          return fn.name;
        },
      });
    }
    // eslint-disable-next-line no-empty
  } catch (_oO) {}

  return sentryWrapped;
}

/**
 * All properties the report dialog supports
 */

exports.WINDOW = WINDOW;
exports.ignoreNextOnError = ignoreNextOnError;
exports.shouldIgnoreOnError = shouldIgnoreOnError;
exports.wrap = wrap;


},{"@sentry/core":24,"@sentry/utils":130}],5:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

require('./exports.js');
const core = require('@sentry/core');
const helpers = require('./helpers.js');
const index = require('./integrations/index.js');
const replay = require('@sentry/replay');
const client = require('./client.js');
const fetch = require('./transports/fetch.js');
const xhr = require('./transports/xhr.js');
const stackParsers = require('./stack-parsers.js');
const eventbuilder = require('./eventbuilder.js');
const sdk = require('./sdk.js');
const globalhandlers = require('./integrations/globalhandlers.js');
const trycatch = require('./integrations/trycatch.js');
const breadcrumbs = require('./integrations/breadcrumbs.js');
const linkederrors = require('./integrations/linkederrors.js');
const httpcontext = require('./integrations/httpcontext.js');
const dedupe = require('./integrations/dedupe.js');

let windowIntegrations = {};

// This block is needed to add compatibility with the integrations packages when used with a CDN
if (helpers.WINDOW.Sentry && helpers.WINDOW.Sentry.Integrations) {
  windowIntegrations = helpers.WINDOW.Sentry.Integrations;
}

const INTEGRATIONS = {
  ...windowIntegrations,
  ...core.Integrations,
  ...index,
};
// __ROLLUP_EXCLUDE_FROM_BUNDLES_END__

exports.FunctionToString = core.FunctionToString;
exports.Hub = core.Hub;
exports.InboundFilters = core.InboundFilters;
exports.SDK_VERSION = core.SDK_VERSION;
exports.Scope = core.Scope;
exports.addBreadcrumb = core.addBreadcrumb;
exports.addGlobalEventProcessor = core.addGlobalEventProcessor;
exports.captureEvent = core.captureEvent;
exports.captureException = core.captureException;
exports.captureMessage = core.captureMessage;
exports.configureScope = core.configureScope;
exports.createTransport = core.createTransport;
exports.getCurrentHub = core.getCurrentHub;
exports.getHubFromCarrier = core.getHubFromCarrier;
exports.makeMain = core.makeMain;
exports.setContext = core.setContext;
exports.setExtra = core.setExtra;
exports.setExtras = core.setExtras;
exports.setTag = core.setTag;
exports.setTags = core.setTags;
exports.setUser = core.setUser;
exports.startTransaction = core.startTransaction;
exports.withScope = core.withScope;
exports.WINDOW = helpers.WINDOW;
exports.Replay = replay.Replay;
exports.BrowserClient = client.BrowserClient;
exports.makeFetchTransport = fetch.makeFetchTransport;
exports.makeXHRTransport = xhr.makeXHRTransport;
exports.chromeStackLineParser = stackParsers.chromeStackLineParser;
exports.defaultStackLineParsers = stackParsers.defaultStackLineParsers;
exports.defaultStackParser = stackParsers.defaultStackParser;
exports.geckoStackLineParser = stackParsers.geckoStackLineParser;
exports.opera10StackLineParser = stackParsers.opera10StackLineParser;
exports.opera11StackLineParser = stackParsers.opera11StackLineParser;
exports.winjsStackLineParser = stackParsers.winjsStackLineParser;
exports.eventFromException = eventbuilder.eventFromException;
exports.eventFromMessage = eventbuilder.eventFromMessage;
exports.close = sdk.close;
exports.defaultIntegrations = sdk.defaultIntegrations;
exports.flush = sdk.flush;
exports.forceLoad = sdk.forceLoad;
exports.init = sdk.init;
exports.lastEventId = sdk.lastEventId;
exports.onLoad = sdk.onLoad;
exports.showReportDialog = sdk.showReportDialog;
exports.wrap = sdk.wrap;
exports.GlobalHandlers = globalhandlers.GlobalHandlers;
exports.TryCatch = trycatch.TryCatch;
exports.Breadcrumbs = breadcrumbs.Breadcrumbs;
exports.LinkedErrors = linkederrors.LinkedErrors;
exports.HttpContext = httpcontext.HttpContext;
exports.Dedupe = dedupe.Dedupe;
exports.Integrations = INTEGRATIONS;


},{"./client.js":1,"./eventbuilder.js":2,"./exports.js":3,"./helpers.js":4,"./integrations/breadcrumbs.js":6,"./integrations/dedupe.js":7,"./integrations/globalhandlers.js":8,"./integrations/httpcontext.js":9,"./integrations/index.js":10,"./integrations/linkederrors.js":11,"./integrations/trycatch.js":12,"./sdk.js":13,"./stack-parsers.js":14,"./transports/fetch.js":15,"./transports/xhr.js":18,"@sentry/core":24,"@sentry/replay":47}],6:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const helpers = require('../helpers.js');

/* eslint-disable @typescript-eslint/no-unsafe-member-access */

/** JSDoc */

/** maxStringLength gets capped to prevent 100 breadcrumbs exceeding 1MB event payload size */
const MAX_ALLOWED_STRING_LENGTH = 1024;

const BREADCRUMB_INTEGRATION_ID = 'Breadcrumbs';

/**
 * Default Breadcrumbs instrumentations
 * TODO: Deprecated - with v6, this will be renamed to `Instrument`
 */
class Breadcrumbs  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = BREADCRUMB_INTEGRATION_ID;}

  /**
   * @inheritDoc
   */
   __init() {this.name = Breadcrumbs.id;}

  /**
   * Options of the breadcrumbs integration.
   */
  // This field is public, because we use it in the browser client to check if the `sentry` option is enabled.

  /**
   * @inheritDoc
   */
   constructor(options) {;Breadcrumbs.prototype.__init.call(this);
    this.options = {
      console: true,
      dom: true,
      fetch: true,
      history: true,
      sentry: true,
      xhr: true,
      ...options,
    };
  }

  /**
   * Instrument browser built-ins w/ breadcrumb capturing
   *  - Console API
   *  - DOM API (click/typing)
   *  - XMLHttpRequest API
   *  - Fetch API
   *  - History API
   */
   setupOnce() {
    if (this.options.console) {
      utils.addInstrumentationHandler('console', _consoleBreadcrumb);
    }
    if (this.options.dom) {
      utils.addInstrumentationHandler('dom', _domBreadcrumb(this.options.dom));
    }
    if (this.options.xhr) {
      utils.addInstrumentationHandler('xhr', _xhrBreadcrumb);
    }
    if (this.options.fetch) {
      utils.addInstrumentationHandler('fetch', _fetchBreadcrumb);
    }
    if (this.options.history) {
      utils.addInstrumentationHandler('history', _historyBreadcrumb);
    }
  }

  /**
   * Adds a breadcrumb for Sentry events or transactions if this option is enabled.
   */
   addSentryBreadcrumb(event) {
    if (this.options.sentry) {
      core.getCurrentHub().addBreadcrumb(
        {
          category: `sentry.${event.type === 'transaction' ? 'transaction' : 'event'}`,
          event_id: event.event_id,
          level: event.level,
          message: utils.getEventDescription(event),
        },
        {
          event,
        },
      );
    }
  }
} Breadcrumbs.__initStatic();

/**
 * A HOC that creaes a function that creates breadcrumbs from DOM API calls.
 * This is a HOC so that we get access to dom options in the closure.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _domBreadcrumb(dom) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function _innerDomBreadcrumb(handlerData) {
    let target;
    let keyAttrs = typeof dom === 'object' ? dom.serializeAttribute : undefined;

    let maxStringLength =
      typeof dom === 'object' && typeof dom.maxStringLength === 'number' ? dom.maxStringLength : undefined;
    if (maxStringLength && maxStringLength > MAX_ALLOWED_STRING_LENGTH) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
        utils.logger.warn(
          `\`dom.maxStringLength\` cannot exceed ${MAX_ALLOWED_STRING_LENGTH}, but a value of ${maxStringLength} was configured. Sentry will use ${MAX_ALLOWED_STRING_LENGTH} instead.`,
        );
      maxStringLength = MAX_ALLOWED_STRING_LENGTH;
    }

    if (typeof keyAttrs === 'string') {
      keyAttrs = [keyAttrs];
    }

    // Accessing event.target can throw (see getsentry/raven-js#838, #768)
    try {
      target = handlerData.event.target
        ? utils.htmlTreeAsString(handlerData.event.target , { keyAttrs, maxStringLength })
        : utils.htmlTreeAsString(handlerData.event , { keyAttrs, maxStringLength });
    } catch (e) {
      target = '<unknown>';
    }

    if (target.length === 0) {
      return;
    }

    core.getCurrentHub().addBreadcrumb(
      {
        category: `ui.${handlerData.name}`,
        message: target,
      },
      {
        event: handlerData.event,
        name: handlerData.name,
        global: handlerData.global,
      },
    );
  }

  return _innerDomBreadcrumb;
}

/**
 * Creates breadcrumbs from console API calls
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _consoleBreadcrumb(handlerData) {
  // This is a hack to fix a Vue3-specific bug that causes an infinite loop of
  // console warnings. This happens when a Vue template is rendered with
  // an undeclared variable, which we try to stringify, ultimately causing
  // Vue to issue another warning which repeats indefinitely.
  // see: https://github.com/getsentry/sentry-javascript/pull/6010
  // see: https://github.com/getsentry/sentry-javascript/issues/5916
  for (let i = 0; i < handlerData.args.length; i++) {
    if (handlerData.args[i] === 'ref=Ref<') {
      handlerData.args[i + 1] = 'viewRef';
      break;
    }
  }
  const breadcrumb = {
    category: 'console',
    data: {
      arguments: handlerData.args,
      logger: 'console',
    },
    level: utils.severityLevelFromString(handlerData.level),
    message: utils.safeJoin(handlerData.args, ' '),
  };

  if (handlerData.level === 'assert') {
    if (handlerData.args[0] === false) {
      breadcrumb.message = `Assertion failed: ${utils.safeJoin(handlerData.args.slice(1), ' ') || 'console.assert'}`;
      breadcrumb.data.arguments = handlerData.args.slice(1);
    } else {
      // Don't capture a breadcrumb for passed assertions
      return;
    }
  }

  core.getCurrentHub().addBreadcrumb(breadcrumb, {
    input: handlerData.args,
    level: handlerData.level,
  });
}

/**
 * Creates breadcrumbs from XHR API calls
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _xhrBreadcrumb(handlerData) {
  if (handlerData.endTimestamp) {
    // We only capture complete, non-sentry requests
    if (handlerData.xhr.__sentry_own_request__) {
      return;
    }

    const { method, url, status_code, body } = handlerData.xhr.__sentry_xhr__ || {};

    core.getCurrentHub().addBreadcrumb(
      {
        category: 'xhr',
        data: {
          method,
          url,
          status_code,
        },
        type: 'http',
      },
      {
        xhr: handlerData.xhr,
        input: body,
      },
    );

    return;
  }
}

/**
 * Creates breadcrumbs from fetch API calls
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _fetchBreadcrumb(handlerData) {
  // We only capture complete fetch requests
  if (!handlerData.endTimestamp) {
    return;
  }

  if (handlerData.fetchData.url.match(/sentry_key/) && handlerData.fetchData.method === 'POST') {
    // We will not create breadcrumbs for fetch requests that contain `sentry_key` (internal sentry requests)
    return;
  }

  if (handlerData.error) {
    core.getCurrentHub().addBreadcrumb(
      {
        category: 'fetch',
        data: handlerData.fetchData,
        level: 'error',
        type: 'http',
      },
      {
        data: handlerData.error,
        input: handlerData.args,
      },
    );
  } else {
    core.getCurrentHub().addBreadcrumb(
      {
        category: 'fetch',
        data: {
          ...handlerData.fetchData,
          status_code: handlerData.response.status,
        },
        type: 'http',
      },
      {
        input: handlerData.args,
        response: handlerData.response,
      },
    );
  }
}

/**
 * Creates breadcrumbs from history API calls
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _historyBreadcrumb(handlerData) {
  let from = handlerData.from;
  let to = handlerData.to;
  const parsedLoc = utils.parseUrl(helpers.WINDOW.location.href);
  let parsedFrom = utils.parseUrl(from);
  const parsedTo = utils.parseUrl(to);

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

  core.getCurrentHub().addBreadcrumb({
    category: 'navigation',
    data: {
      from,
      to,
    },
  });
}

exports.BREADCRUMB_INTEGRATION_ID = BREADCRUMB_INTEGRATION_ID;
exports.Breadcrumbs = Breadcrumbs;


},{"../helpers.js":4,"@sentry/core":24,"@sentry/utils":130}],7:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

/** Deduplication filter */
class Dedupe  {constructor() { Dedupe.prototype.__init.call(this); }
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Dedupe';}

  /**
   * @inheritDoc
   */
   __init() {this.name = Dedupe.id;}

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
   setupOnce(addGlobalEventProcessor, getCurrentHub) {
    const eventProcessor = currentEvent => {
      const self = getCurrentHub().getIntegration(Dedupe);
      if (self) {
        // Juuust in case something goes wrong
        try {
          if (_shouldDropEvent(currentEvent, self._previousEvent)) {
            (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn('Event dropped due to being a duplicate of previously captured event.');
            return null;
          }
        } catch (_oO) {
          return (self._previousEvent = currentEvent);
        }

        return (self._previousEvent = currentEvent);
      }
      return currentEvent;
    };

    eventProcessor.id = this.name;
    addGlobalEventProcessor(eventProcessor);
  }
} Dedupe.__initStatic();

/** JSDoc */
function _shouldDropEvent(currentEvent, previousEvent) {
  if (!previousEvent) {
    return false;
  }

  if (_isSameMessageEvent(currentEvent, previousEvent)) {
    return true;
  }

  if (_isSameExceptionEvent(currentEvent, previousEvent)) {
    return true;
  }

  return false;
}

/** JSDoc */
function _isSameMessageEvent(currentEvent, previousEvent) {
  const currentMessage = currentEvent.message;
  const previousMessage = previousEvent.message;

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

  if (!_isSameFingerprint(currentEvent, previousEvent)) {
    return false;
  }

  if (!_isSameStacktrace(currentEvent, previousEvent)) {
    return false;
  }

  return true;
}

/** JSDoc */
function _isSameExceptionEvent(currentEvent, previousEvent) {
  const previousException = _getExceptionFromEvent(previousEvent);
  const currentException = _getExceptionFromEvent(currentEvent);

  if (!previousException || !currentException) {
    return false;
  }

  if (previousException.type !== currentException.type || previousException.value !== currentException.value) {
    return false;
  }

  if (!_isSameFingerprint(currentEvent, previousEvent)) {
    return false;
  }

  if (!_isSameStacktrace(currentEvent, previousEvent)) {
    return false;
  }

  return true;
}

/** JSDoc */
function _isSameStacktrace(currentEvent, previousEvent) {
  let currentFrames = _getFramesFromEvent(currentEvent);
  let previousFrames = _getFramesFromEvent(previousEvent);

  // If neither event has a stacktrace, they are assumed to be the same
  if (!currentFrames && !previousFrames) {
    return true;
  }

  // If only one event has a stacktrace, but not the other one, they are not the same
  if ((currentFrames && !previousFrames) || (!currentFrames && previousFrames)) {
    return false;
  }

  currentFrames = currentFrames ;
  previousFrames = previousFrames ;

  // If number of frames differ, they are not the same
  if (previousFrames.length !== currentFrames.length) {
    return false;
  }

  // Otherwise, compare the two
  for (let i = 0; i < previousFrames.length; i++) {
    const frameA = previousFrames[i];
    const frameB = currentFrames[i];

    if (
      frameA.filename !== frameB.filename ||
      frameA.lineno !== frameB.lineno ||
      frameA.colno !== frameB.colno ||
      frameA.function !== frameB.function
    ) {
      return false;
    }
  }

  return true;
}

/** JSDoc */
function _isSameFingerprint(currentEvent, previousEvent) {
  let currentFingerprint = currentEvent.fingerprint;
  let previousFingerprint = previousEvent.fingerprint;

  // If neither event has a fingerprint, they are assumed to be the same
  if (!currentFingerprint && !previousFingerprint) {
    return true;
  }

  // If only one event has a fingerprint, but not the other one, they are not the same
  if ((currentFingerprint && !previousFingerprint) || (!currentFingerprint && previousFingerprint)) {
    return false;
  }

  currentFingerprint = currentFingerprint ;
  previousFingerprint = previousFingerprint ;

  // Otherwise, compare the two
  try {
    return !!(currentFingerprint.join('') === previousFingerprint.join(''));
  } catch (_oO) {
    return false;
  }
}

/** JSDoc */
function _getExceptionFromEvent(event) {
  return event.exception && event.exception.values && event.exception.values[0];
}

/** JSDoc */
function _getFramesFromEvent(event) {
  const exception = event.exception;

  if (exception) {
    try {
      // @ts-ignore Object could be undefined
      return exception.values[0].stacktrace.frames;
    } catch (_oO) {
      return undefined;
    }
  }
  return undefined;
}

exports.Dedupe = Dedupe;


},{"@sentry/utils":130}],8:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const eventbuilder = require('../eventbuilder.js');
const helpers = require('../helpers.js');

/* eslint-disable @typescript-eslint/no-unsafe-member-access */

/** Global handlers */
class GlobalHandlers  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'GlobalHandlers';}

  /**
   * @inheritDoc
   */
   __init() {this.name = GlobalHandlers.id;}

  /** JSDoc */

  /**
   * Stores references functions to installing handlers. Will set to undefined
   * after they have been run so that they are not used twice.
   */
   __init2() {this._installFunc = {
    onerror: _installGlobalOnErrorHandler,
    onunhandledrejection: _installGlobalOnUnhandledRejectionHandler,
  };}

  /** JSDoc */
   constructor(options) {;GlobalHandlers.prototype.__init.call(this);GlobalHandlers.prototype.__init2.call(this);
    this._options = {
      onerror: true,
      onunhandledrejection: true,
      ...options,
    };
  }
  /**
   * @inheritDoc
   */
   setupOnce() {
    Error.stackTraceLimit = 50;
    const options = this._options;

    // We can disable guard-for-in as we construct the options object above + do checks against
    // `this._installFunc` for the property.
    // eslint-disable-next-line guard-for-in
    for (const key in options) {
      const installFunc = this._installFunc[key ];
      if (installFunc && options[key ]) {
        globalHandlerLog(key);
        installFunc();
        this._installFunc[key ] = undefined;
      }
    }
  }
} GlobalHandlers.__initStatic();

/** JSDoc */
function _installGlobalOnErrorHandler() {
  utils.addInstrumentationHandler(
    'error',
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (data) => {
      const [hub, stackParser, attachStacktrace] = getHubAndOptions();
      if (!hub.getIntegration(GlobalHandlers)) {
        return;
      }
      const { msg, url, line, column, error } = data;
      if (helpers.shouldIgnoreOnError() || (error && error.__sentry_own_request__)) {
        return;
      }

      const event =
        error === undefined && utils.isString(msg)
          ? _eventFromIncompleteOnError(msg, url, line, column)
          : _enhanceEventWithInitialFrame(
              eventbuilder.eventFromUnknownInput(stackParser, error || msg, undefined, attachStacktrace, false),
              url,
              line,
              column,
            );

      event.level = 'error';

      addMechanismAndCapture(hub, error, event, 'onerror');
    },
  );
}

/** JSDoc */
function _installGlobalOnUnhandledRejectionHandler() {
  utils.addInstrumentationHandler(
    'unhandledrejection',
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e) => {
      const [hub, stackParser, attachStacktrace] = getHubAndOptions();
      if (!hub.getIntegration(GlobalHandlers)) {
        return;
      }
      let error = e;

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
      } catch (_oO) {
        // no-empty
      }

      if (helpers.shouldIgnoreOnError() || (error && error.__sentry_own_request__)) {
        return true;
      }

      const event = utils.isPrimitive(error)
        ? _eventFromRejectionWithPrimitive(error)
        : eventbuilder.eventFromUnknownInput(stackParser, error, undefined, attachStacktrace, true);

      event.level = 'error';

      addMechanismAndCapture(hub, error, event, 'onunhandledrejection');
      return;
    },
  );
}

/**
 * Create an event from a promise rejection where the `reason` is a primitive.
 *
 * @param reason: The `reason` property of the promise rejection
 * @returns An Event object with an appropriate `exception` value
 */
function _eventFromRejectionWithPrimitive(reason) {
  return {
    exception: {
      values: [
        {
          type: 'UnhandledRejection',
          // String() is needed because the Primitive type includes symbols (which can't be automatically stringified)
          value: `Non-Error promise rejection captured with value: ${String(reason)}`,
        },
      ],
    },
  };
}

/**
 * This function creates a stack from an old, error-less onerror handler.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _eventFromIncompleteOnError(msg, url, line, column) {
  const ERROR_TYPES_RE =
    /^(?:[Uu]ncaught (?:exception: )?)?(?:((?:Eval|Internal|Range|Reference|Syntax|Type|URI|)Error): )?(.*)$/i;

  // If 'message' is ErrorEvent, get real message from inside
  let message = utils.isErrorEvent(msg) ? msg.message : msg;
  let name = 'Error';

  const groups = message.match(ERROR_TYPES_RE);
  if (groups) {
    name = groups[1];
    message = groups[2];
  }

  const event = {
    exception: {
      values: [
        {
          type: name,
          value: message,
        },
      ],
    },
  };

  return _enhanceEventWithInitialFrame(event, url, line, column);
}

/** JSDoc */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _enhanceEventWithInitialFrame(event, url, line, column) {
  // event.exception
  const e = (event.exception = event.exception || {});
  // event.exception.values
  const ev = (e.values = e.values || []);
  // event.exception.values[0]
  const ev0 = (ev[0] = ev[0] || {});
  // event.exception.values[0].stacktrace
  const ev0s = (ev0.stacktrace = ev0.stacktrace || {});
  // event.exception.values[0].stacktrace.frames
  const ev0sf = (ev0s.frames = ev0s.frames || []);

  const colno = isNaN(parseInt(column, 10)) ? undefined : column;
  const lineno = isNaN(parseInt(line, 10)) ? undefined : line;
  const filename = utils.isString(url) && url.length > 0 ? url : utils.getLocationHref();

  // event.exception.values[0].stacktrace.frames
  if (ev0sf.length === 0) {
    ev0sf.push({
      colno,
      filename,
      function: '?',
      in_app: true,
      lineno,
    });
  }

  return event;
}

function globalHandlerLog(type) {
  (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log(`Global Handler attached: ${type}`);
}

function addMechanismAndCapture(hub, error, event, type) {
  utils.addExceptionMechanism(event, {
    handled: false,
    type,
  });
  hub.captureEvent(event, {
    originalException: error,
  });
}

function getHubAndOptions() {
  const hub = core.getCurrentHub();
  const client = hub.getClient();
  const options = (client && client.getOptions()) || {
    stackParser: () => [],
    attachStacktrace: false,
  };
  return [hub, options.stackParser, options.attachStacktrace];
}

exports.GlobalHandlers = GlobalHandlers;


},{"../eventbuilder.js":2,"../helpers.js":4,"@sentry/core":24,"@sentry/utils":130}],9:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const helpers = require('../helpers.js');

/** HttpContext integration collects information about HTTP request headers */
class HttpContext  {constructor() { HttpContext.prototype.__init.call(this); }
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'HttpContext';}

  /**
   * @inheritDoc
   */
   __init() {this.name = HttpContext.id;}

  /**
   * @inheritDoc
   */
   setupOnce() {
    core.addGlobalEventProcessor((event) => {
      if (core.getCurrentHub().getIntegration(HttpContext)) {
        // if none of the information we want exists, don't bother
        if (!helpers.WINDOW.navigator && !helpers.WINDOW.location && !helpers.WINDOW.document) {
          return event;
        }

        // grab as much info as exists and add it to the event
        const url = (event.request && event.request.url) || (helpers.WINDOW.location && helpers.WINDOW.location.href);
        const { referrer } = helpers.WINDOW.document || {};
        const { userAgent } = helpers.WINDOW.navigator || {};

        const headers = {
          ...(event.request && event.request.headers),
          ...(referrer && { Referer: referrer }),
          ...(userAgent && { 'User-Agent': userAgent }),
        };
        const request = { ...(url && { url }), headers };

        return { ...event, request };
      }
      return event;
    });
  }
} HttpContext.__initStatic();

exports.HttpContext = HttpContext;


},{"../helpers.js":4,"@sentry/core":24}],10:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const globalhandlers = require('./globalhandlers.js');
const trycatch = require('./trycatch.js');
const breadcrumbs = require('./breadcrumbs.js');
const linkederrors = require('./linkederrors.js');
const httpcontext = require('./httpcontext.js');
const dedupe = require('./dedupe.js');



exports.GlobalHandlers = globalhandlers.GlobalHandlers;
exports.TryCatch = trycatch.TryCatch;
exports.Breadcrumbs = breadcrumbs.Breadcrumbs;
exports.LinkedErrors = linkederrors.LinkedErrors;
exports.HttpContext = httpcontext.HttpContext;
exports.Dedupe = dedupe.Dedupe;


},{"./breadcrumbs.js":6,"./dedupe.js":7,"./globalhandlers.js":8,"./httpcontext.js":9,"./linkederrors.js":11,"./trycatch.js":12}],11:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const eventbuilder = require('../eventbuilder.js');

const DEFAULT_KEY = 'cause';
const DEFAULT_LIMIT = 5;

/** Adds SDK info to an event. */
class LinkedErrors  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'LinkedErrors';}

  /**
   * @inheritDoc
   */
    __init() {this.name = LinkedErrors.id;}

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
   constructor(options = {}) {;LinkedErrors.prototype.__init.call(this);
    this._key = options.key || DEFAULT_KEY;
    this._limit = options.limit || DEFAULT_LIMIT;
  }

  /**
   * @inheritDoc
   */
   setupOnce() {
    const client = core.getCurrentHub().getClient();
    if (!client) {
      return;
    }
    core.addGlobalEventProcessor((event, hint) => {
      const self = core.getCurrentHub().getIntegration(LinkedErrors);
      return self ? _handler(client.getOptions().stackParser, self._key, self._limit, event, hint) : event;
    });
  }
} LinkedErrors.__initStatic();

/**
 * @inheritDoc
 */
function _handler(
  parser,
  key,
  limit,
  event,
  hint,
) {
  if (!event.exception || !event.exception.values || !hint || !utils.isInstanceOf(hint.originalException, Error)) {
    return event;
  }
  const linkedErrors = _walkErrorTree(parser, limit, hint.originalException , key);
  event.exception.values = [...linkedErrors, ...event.exception.values];
  return event;
}

/**
 * JSDOC
 */
function _walkErrorTree(
  parser,
  limit,
  error,
  key,
  stack = [],
) {
  if (!utils.isInstanceOf(error[key], Error) || stack.length + 1 >= limit) {
    return stack;
  }
  const exception = eventbuilder.exceptionFromError(parser, error[key]);
  return _walkErrorTree(parser, limit, error[key], key, [exception, ...stack]);
}

exports.LinkedErrors = LinkedErrors;
exports._handler = _handler;
exports._walkErrorTree = _walkErrorTree;


},{"../eventbuilder.js":2,"@sentry/core":24,"@sentry/utils":130}],12:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const helpers = require('../helpers.js');

const DEFAULT_EVENT_TARGET = [
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
class TryCatch  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'TryCatch';}

  /**
   * @inheritDoc
   */
   __init() {this.name = TryCatch.id;}

  /** JSDoc */

  /**
   * @inheritDoc
   */
   constructor(options) {;TryCatch.prototype.__init.call(this);
    this._options = {
      XMLHttpRequest: true,
      eventTarget: true,
      requestAnimationFrame: true,
      setInterval: true,
      setTimeout: true,
      ...options,
    };
  }

  /**
   * Wrap timer functions and event targets to catch errors
   * and provide better metadata.
   */
   setupOnce() {
    if (this._options.setTimeout) {
      utils.fill(helpers.WINDOW, 'setTimeout', _wrapTimeFunction);
    }

    if (this._options.setInterval) {
      utils.fill(helpers.WINDOW, 'setInterval', _wrapTimeFunction);
    }

    if (this._options.requestAnimationFrame) {
      utils.fill(helpers.WINDOW, 'requestAnimationFrame', _wrapRAF);
    }

    if (this._options.XMLHttpRequest && 'XMLHttpRequest' in helpers.WINDOW) {
      utils.fill(XMLHttpRequest.prototype, 'send', _wrapXHR);
    }

    const eventTargetOption = this._options.eventTarget;
    if (eventTargetOption) {
      const eventTarget = Array.isArray(eventTargetOption) ? eventTargetOption : DEFAULT_EVENT_TARGET;
      eventTarget.forEach(_wrapEventTarget);
    }
  }
} TryCatch.__initStatic();

/** JSDoc */
function _wrapTimeFunction(original) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function ( ...args) {
    const originalCallback = args[0];
    args[0] = helpers.wrap(originalCallback, {
      mechanism: {
        data: { function: utils.getFunctionName(original) },
        handled: true,
        type: 'instrument',
      },
    });
    return original.apply(this, args);
  };
}

/** JSDoc */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _wrapRAF(original) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function ( callback) {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    return original.apply(this, [
      helpers.wrap(callback, {
        mechanism: {
          data: {
            function: 'requestAnimationFrame',
            handler: utils.getFunctionName(original),
          },
          handled: true,
          type: 'instrument',
        },
      }),
    ]);
  };
}

/** JSDoc */
function _wrapXHR(originalSend) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function ( ...args) {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const xhr = this;
    const xmlHttpRequestProps = ['onload', 'onerror', 'onprogress', 'onreadystatechange'];

    xmlHttpRequestProps.forEach(prop => {
      if (prop in xhr && typeof xhr[prop] === 'function') {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        utils.fill(xhr, prop, function (original) {
          const wrapOptions = {
            mechanism: {
              data: {
                function: prop,
                handler: utils.getFunctionName(original),
              },
              handled: true,
              type: 'instrument',
            },
          };

          // If Instrument integration has been called before TryCatch, get the name of original function
          const originalFunction = utils.getOriginalFunction(original);
          if (originalFunction) {
            wrapOptions.mechanism.data.handler = utils.getFunctionName(originalFunction);
          }

          // Otherwise wrap directly
          return helpers.wrap(original, wrapOptions);
        });
      }
    });

    return originalSend.apply(this, args);
  };
}

/** JSDoc */
function _wrapEventTarget(target) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globalObject = helpers.WINDOW ;
  // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
  const proto = globalObject[target] && globalObject[target].prototype;

  // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access, no-prototype-builtins
  if (!proto || !proto.hasOwnProperty || !proto.hasOwnProperty('addEventListener')) {
    return;
  }

  utils.fill(proto, 'addEventListener', function (original)

 {
    return function (
      // eslint-disable-next-line @typescript-eslint/no-explicit-any

      eventName,
      fn,
      options,
    ) {
      try {
        if (typeof fn.handleEvent === 'function') {
          // ESlint disable explanation:
          //  First, it is generally safe to call `wrap` with an unbound function. Furthermore, using `.bind()` would
          //  introduce a bug here, because bind returns a new function that doesn't have our
          //  flags(like __sentry_original__) attached. `wrap` checks for those flags to avoid unnecessary wrapping.
          //  Without those flags, every call to addEventListener wraps the function again, causing a memory leak.
          // eslint-disable-next-line @typescript-eslint/unbound-method
          fn.handleEvent = helpers.wrap(fn.handleEvent, {
            mechanism: {
              data: {
                function: 'handleEvent',
                handler: utils.getFunctionName(fn),
                target,
              },
              handled: true,
              type: 'instrument',
            },
          });
        }
      } catch (err) {
        // can sometimes get 'Permission denied to access property "handle Event'
      }

      return original.apply(this, [
        eventName,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        helpers.wrap(fn , {
          mechanism: {
            data: {
              function: 'addEventListener',
              handler: utils.getFunctionName(fn),
              target,
            },
            handled: true,
            type: 'instrument',
          },
        }),
        options,
      ]);
    };
  });

  utils.fill(
    proto,
    'removeEventListener',
    function (
      originalRemoveEventListener,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ) {
      return function (
        // eslint-disable-next-line @typescript-eslint/no-explicit-any

        eventName,
        fn,
        options,
      ) {
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
        const wrappedEventHandler = fn ;
        try {
          const originalEventHandler = wrappedEventHandler && wrappedEventHandler.__sentry_wrapped__;
          if (originalEventHandler) {
            originalRemoveEventListener.call(this, eventName, originalEventHandler, options);
          }
        } catch (e) {
          // ignore, accessing __sentry_wrapped__ will throw in some Selenium environments
        }
        return originalRemoveEventListener.call(this, eventName, wrappedEventHandler, options);
      };
    },
  );
}

exports.TryCatch = TryCatch;


},{"../helpers.js":4,"@sentry/utils":130}],13:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const client = require('./client.js');
const helpers = require('./helpers.js');
require('./integrations/index.js');
const stackParsers = require('./stack-parsers.js');
require('./transports/index.js');
const trycatch = require('./integrations/trycatch.js');
const breadcrumbs = require('./integrations/breadcrumbs.js');
const globalhandlers = require('./integrations/globalhandlers.js');
const linkederrors = require('./integrations/linkederrors.js');
const dedupe = require('./integrations/dedupe.js');
const httpcontext = require('./integrations/httpcontext.js');
const fetch = require('./transports/fetch.js');
const xhr = require('./transports/xhr.js');

const defaultIntegrations = [
  new core.Integrations.InboundFilters(),
  new core.Integrations.FunctionToString(),
  new trycatch.TryCatch(),
  new breadcrumbs.Breadcrumbs(),
  new globalhandlers.GlobalHandlers(),
  new linkederrors.LinkedErrors(),
  new dedupe.Dedupe(),
  new httpcontext.HttpContext(),
];

/**
 * A magic string that build tooling can leverage in order to inject a release value into the SDK.
 */

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
function init(options = {}) {
  if (options.defaultIntegrations === undefined) {
    options.defaultIntegrations = defaultIntegrations;
  }
  if (options.release === undefined) {
    // This allows build tooling to find-and-replace __SENTRY_RELEASE__ to inject a release value
    if (typeof __SENTRY_RELEASE__ === 'string') {
      options.release = __SENTRY_RELEASE__;
    }

    // This supports the variable that sentry-webpack-plugin injects
    if (helpers.WINDOW.SENTRY_RELEASE && helpers.WINDOW.SENTRY_RELEASE.id) {
      options.release = helpers.WINDOW.SENTRY_RELEASE.id;
    }
  }
  if (options.autoSessionTracking === undefined) {
    options.autoSessionTracking = true;
  }
  if (options.sendClientReports === undefined) {
    options.sendClientReports = true;
  }

  const clientOptions = {
    ...options,
    stackParser: utils.stackParserFromStackParserOptions(options.stackParser || stackParsers.defaultStackParser),
    integrations: core.getIntegrationsToSetup(options),
    transport: options.transport || (utils.supportsFetch() ? fetch.makeFetchTransport : xhr.makeXHRTransport),
  };

  core.initAndBind(client.BrowserClient, clientOptions);

  if (options.autoSessionTracking) {
    startSessionTracking();
  }
}

/**
 * Present the user with a report dialog.
 *
 * @param options Everything is optional, we try to fetch all info need from the global scope.
 */
function showReportDialog(options = {}, hub = core.getCurrentHub()) {
  // doesn't work without a document (React Native)
  if (!helpers.WINDOW.document) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('Global document not defined in showReportDialog call');
    return;
  }

  const { client, scope } = hub.getStackTop();
  const dsn = options.dsn || (client && client.getDsn());
  if (!dsn) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('DSN not configured for showReportDialog call');
    return;
  }

  if (scope) {
    options.user = {
      ...scope.getUser(),
      ...options.user,
    };
  }

  if (!options.eventId) {
    options.eventId = hub.lastEventId();
  }

  const script = helpers.WINDOW.document.createElement('script');
  script.async = true;
  script.src = core.getReportDialogEndpoint(dsn, options);

  if (options.onLoad) {
    // eslint-disable-next-line @typescript-eslint/unbound-method
    script.onload = options.onLoad;
  }

  const injectionPoint = helpers.WINDOW.document.head || helpers.WINDOW.document.body;
  if (injectionPoint) {
    injectionPoint.appendChild(script);
  } else {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('Not injecting report dialog. No injection point found in HTML');
  }
}

/**
 * This is the getter for lastEventId.
 *
 * @returns The last event id of a captured event.
 */
function lastEventId() {
  return core.getCurrentHub().lastEventId();
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
  const client = core.getCurrentHub().getClient();
  if (client) {
    return client.flush(timeout);
  }
  (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn('Cannot flush events. No client defined.');
  return utils.resolvedSyncPromise(false);
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
  const client = core.getCurrentHub().getClient();
  if (client) {
    return client.close(timeout);
  }
  (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn('Cannot flush events and disable SDK. No client defined.');
  return utils.resolvedSyncPromise(false);
}

/**
 * Wrap code within a try/catch block so the SDK is able to capture errors.
 *
 * @param fn A function to wrap.
 *
 * @returns The result of wrapped function call.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function wrap(fn) {
  return helpers.wrap(fn)();
}

function startSessionOnHub(hub) {
  hub.startSession({ ignoreDuration: true });
  hub.captureSession();
}

/**
 * Enable automatic Session Tracking for the initial page load.
 */
function startSessionTracking() {
  if (typeof helpers.WINDOW.document === 'undefined') {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
      utils.logger.warn('Session tracking in non-browser environment with @sentry/browser is not supported.');
    return;
  }

  const hub = core.getCurrentHub();

  // The only way for this to be false is for there to be a version mismatch between @sentry/browser (>= 6.0.0) and
  // @sentry/hub (< 5.27.0). In the simple case, there won't ever be such a mismatch, because the two packages are
  // pinned at the same version in package.json, but there are edge cases where it's possible. See
  // https://github.com/getsentry/sentry-javascript/issues/3207 and
  // https://github.com/getsentry/sentry-javascript/issues/3234 and
  // https://github.com/getsentry/sentry-javascript/issues/3278.
  if (!hub.captureSession) {
    return;
  }

  // The session duration for browser sessions does not track a meaningful
  // concept that can be used as a metric.
  // Automatically captured sessions are akin to page views, and thus we
  // discard their duration.
  startSessionOnHub(hub);

  // We want to create a session for every navigation as well
  utils.addInstrumentationHandler('history', ({ from, to }) => {
    // Don't create an additional session for the initial route or if the location did not change
    if (!(from === undefined || from === to)) {
      startSessionOnHub(core.getCurrentHub());
    }
  });
}

exports.close = close;
exports.defaultIntegrations = defaultIntegrations;
exports.flush = flush;
exports.forceLoad = forceLoad;
exports.init = init;
exports.lastEventId = lastEventId;
exports.onLoad = onLoad;
exports.showReportDialog = showReportDialog;
exports.wrap = wrap;


},{"./client.js":1,"./helpers.js":4,"./integrations/breadcrumbs.js":6,"./integrations/dedupe.js":7,"./integrations/globalhandlers.js":8,"./integrations/httpcontext.js":9,"./integrations/index.js":10,"./integrations/linkederrors.js":11,"./integrations/trycatch.js":12,"./stack-parsers.js":14,"./transports/fetch.js":15,"./transports/index.js":16,"./transports/xhr.js":18,"@sentry/core":24,"@sentry/utils":130}],14:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

// global reference to slice
const UNKNOWN_FUNCTION = '?';

const OPERA10_PRIORITY = 10;
const OPERA11_PRIORITY = 20;
const CHROME_PRIORITY = 30;
const WINJS_PRIORITY = 40;
const GECKO_PRIORITY = 50;

function createFrame(filename, func, lineno, colno) {
  const frame = {
    filename,
    function: func,
    // All browser frames are considered in_app
    in_app: true,
  };

  if (lineno !== undefined) {
    frame.lineno = lineno;
  }

  if (colno !== undefined) {
    frame.colno = colno;
  }

  return frame;
}

// Chromium based browsers: Chrome, Brave, new Opera, new Edge
const chromeRegex =
  /^\s*at (?:(.*\).*?|.*?) ?\((?:address at )?)?((?:file|https?|blob|chrome-extension|address|native|eval|webpack|<anonymous>|[-a-z]+:|.*bundle|\/)?.*?)(?::(\d+))?(?::(\d+))?\)?\s*$/i;
const chromeEvalRegex = /\((\S*)(?::(\d+))(?::(\d+))\)/;

const chrome = line => {
  const parts = chromeRegex.exec(line);

  if (parts) {
    const isEval = parts[2] && parts[2].indexOf('eval') === 0; // start of line

    if (isEval) {
      const subMatch = chromeEvalRegex.exec(parts[2]);

      if (subMatch) {
        // throw out eval line/column and use top-most line/column number
        parts[2] = subMatch[1]; // url
        parts[3] = subMatch[2]; // line
        parts[4] = subMatch[3]; // column
      }
    }

    // Kamil: One more hack won't hurt us right? Understanding and adding more rules on top of these regexps right now
    // would be way too time consuming. (TODO: Rewrite whole RegExp to be more readable)
    const [func, filename] = extractSafariExtensionDetails(parts[1] || UNKNOWN_FUNCTION, parts[2]);

    return createFrame(filename, func, parts[3] ? +parts[3] : undefined, parts[4] ? +parts[4] : undefined);
  }

  return;
};

const chromeStackLineParser = [CHROME_PRIORITY, chrome];

// gecko regex: `(?:bundle|\d+\.js)`: `bundle` is for react native, `\d+\.js` also but specifically for ram bundles because it
// generates filenames without a prefix like `file://` the filenames in the stacktrace are just 42.js
// We need this specific case for now because we want no other regex to match.
const geckoREgex =
  /^\s*(.*?)(?:\((.*?)\))?(?:^|@)?((?:file|https?|blob|chrome|webpack|resource|moz-extension|safari-extension|safari-web-extension|capacitor)?:\/.*?|\[native code\]|[^@]*(?:bundle|\d+\.js)|\/[\w\-. /=]+)(?::(\d+))?(?::(\d+))?\s*$/i;
const geckoEvalRegex = /(\S+) line (\d+)(?: > eval line \d+)* > eval/i;

const gecko = line => {
  const parts = geckoREgex.exec(line);

  if (parts) {
    const isEval = parts[3] && parts[3].indexOf(' > eval') > -1;
    if (isEval) {
      const subMatch = geckoEvalRegex.exec(parts[3]);

      if (subMatch) {
        // throw out eval line/column and use top-most line number
        parts[1] = parts[1] || 'eval';
        parts[3] = subMatch[1];
        parts[4] = subMatch[2];
        parts[5] = ''; // no column when eval
      }
    }

    let filename = parts[3];
    let func = parts[1] || UNKNOWN_FUNCTION;
    [func, filename] = extractSafariExtensionDetails(func, filename);

    return createFrame(filename, func, parts[4] ? +parts[4] : undefined, parts[5] ? +parts[5] : undefined);
  }

  return;
};

const geckoStackLineParser = [GECKO_PRIORITY, gecko];

const winjsRegex =
  /^\s*at (?:((?:\[object object\])?.+) )?\(?((?:file|ms-appx|https?|webpack|blob):.*?):(\d+)(?::(\d+))?\)?\s*$/i;

const winjs = line => {
  const parts = winjsRegex.exec(line);

  return parts
    ? createFrame(parts[2], parts[1] || UNKNOWN_FUNCTION, +parts[3], parts[4] ? +parts[4] : undefined)
    : undefined;
};

const winjsStackLineParser = [WINJS_PRIORITY, winjs];

const opera10Regex = / line (\d+).*script (?:in )?(\S+)(?:: in function (\S+))?$/i;

const opera10 = line => {
  const parts = opera10Regex.exec(line);
  return parts ? createFrame(parts[2], parts[3] || UNKNOWN_FUNCTION, +parts[1]) : undefined;
};

const opera10StackLineParser = [OPERA10_PRIORITY, opera10];

const opera11Regex =
  / line (\d+), column (\d+)\s*(?:in (?:<anonymous function: ([^>]+)>|([^)]+))\(.*\))? in (.*):\s*$/i;

const opera11 = line => {
  const parts = opera11Regex.exec(line);
  return parts ? createFrame(parts[5], parts[3] || parts[4] || UNKNOWN_FUNCTION, +parts[1], +parts[2]) : undefined;
};

const opera11StackLineParser = [OPERA11_PRIORITY, opera11];

const defaultStackLineParsers = [chromeStackLineParser, geckoStackLineParser, winjsStackLineParser];

const defaultStackParser = utils.createStackParser(...defaultStackLineParsers);

/**
 * Safari web extensions, starting version unknown, can produce "frames-only" stacktraces.
 * What it means, is that instead of format like:
 *
 * Error: wat
 *   at function@url:row:col
 *   at function@url:row:col
 *   at function@url:row:col
 *
 * it produces something like:
 *
 *   function@url:row:col
 *   function@url:row:col
 *   function@url:row:col
 *
 * Because of that, it won't be captured by `chrome` RegExp and will fall into `Gecko` branch.
 * This function is extracted so that we can use it in both places without duplicating the logic.
 * Unfortunately "just" changing RegExp is too complicated now and making it pass all tests
 * and fix this case seems like an impossible, or at least way too time-consuming task.
 */
const extractSafariExtensionDetails = (func, filename) => {
  const isSafariExtension = func.indexOf('safari-extension') !== -1;
  const isSafariWebExtension = func.indexOf('safari-web-extension') !== -1;

  return isSafariExtension || isSafariWebExtension
    ? [
        func.indexOf('@') !== -1 ? func.split('@')[0] : UNKNOWN_FUNCTION,
        isSafariExtension ? `safari-extension:${filename}` : `safari-web-extension:${filename}`,
      ]
    : [func, filename];
};

exports.chromeStackLineParser = chromeStackLineParser;
exports.defaultStackLineParsers = defaultStackLineParsers;
exports.defaultStackParser = defaultStackParser;
exports.geckoStackLineParser = geckoStackLineParser;
exports.opera10StackLineParser = opera10StackLineParser;
exports.opera11StackLineParser = opera11StackLineParser;
exports.winjsStackLineParser = winjsStackLineParser;


},{"@sentry/utils":130}],15:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils$1 = require('@sentry/utils');
const utils = require('./utils.js');

/**
 * Creates a Transport that uses the Fetch API to send events to Sentry.
 */
function makeFetchTransport(
  options,
  nativeFetch = utils.getNativeFetchImplementation(),
) {
  function makeRequest(request) {
    const requestOptions = {
      body: request.body,
      method: 'POST',
      referrerPolicy: 'origin',
      headers: options.headers,
      // Outgoing requests are usually cancelled when navigating to a different page, causing a "TypeError: Failed to
      // fetch" error and sending a "network_error" client-outcome - in Chrome, the request status shows "(cancelled)".
      // The `keepalive` flag keeps outgoing requests alive, even when switching pages. We want this since we're
      // frequently sending events right before the user is switching pages (eg. whenfinishing navigation transactions).
      // Gotchas:
      // - `keepalive` isn't supported by Firefox
      // - As per spec (https://fetch.spec.whatwg.org/#http-network-or-cache-fetch), a request with `keepalive: true`
      //   and a content length of > 64 kibibytes returns a network error. We will therefore only activate the flag when
      //   we're below that limit.
      keepalive: request.body.length <= 65536,
      ...options.fetchOptions,
    };

    try {
      return nativeFetch(options.url, requestOptions).then(response => ({
        statusCode: response.status,
        headers: {
          'x-sentry-rate-limits': response.headers.get('X-Sentry-Rate-Limits'),
          'retry-after': response.headers.get('Retry-After'),
        },
      }));
    } catch (e) {
      utils.clearCachedFetchImplementation();
      return utils$1.rejectedSyncPromise(e);
    }
  }

  return core.createTransport(options, makeRequest);
}

exports.makeFetchTransport = makeFetchTransport;


},{"./utils.js":17,"@sentry/core":24,"@sentry/utils":130}],16:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const fetch = require('./fetch.js');
const xhr = require('./xhr.js');



exports.makeFetchTransport = fetch.makeFetchTransport;
exports.makeXHRTransport = xhr.makeXHRTransport;


},{"./fetch.js":15,"./xhr.js":18}],17:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const helpers = require('../helpers.js');

let cachedFetchImpl = undefined;

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
  if (cachedFetchImpl) {
    return cachedFetchImpl;
  }

  /* eslint-disable @typescript-eslint/unbound-method */

  // Fast path to avoid DOM I/O
  if (utils.isNativeFetch(helpers.WINDOW.fetch)) {
    return (cachedFetchImpl = helpers.WINDOW.fetch.bind(helpers.WINDOW));
  }

  const document = helpers.WINDOW.document;
  let fetchImpl = helpers.WINDOW.fetch;
  // eslint-disable-next-line deprecation/deprecation
  if (document && typeof document.createElement === 'function') {
    try {
      const sandbox = document.createElement('iframe');
      sandbox.hidden = true;
      document.head.appendChild(sandbox);
      const contentWindow = sandbox.contentWindow;
      if (contentWindow && contentWindow.fetch) {
        fetchImpl = contentWindow.fetch;
      }
      document.head.removeChild(sandbox);
    } catch (e) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
        utils.logger.warn('Could not create sandbox iframe for pure fetch check, bailing to window.fetch: ', e);
    }
  }

  return (cachedFetchImpl = fetchImpl.bind(helpers.WINDOW));
  /* eslint-enable @typescript-eslint/unbound-method */
}

/** Clears cached fetch impl */
function clearCachedFetchImplementation() {
  cachedFetchImpl = undefined;
}

exports.clearCachedFetchImplementation = clearCachedFetchImplementation;
exports.getNativeFetchImplementation = getNativeFetchImplementation;


},{"../helpers.js":4,"@sentry/utils":130}],18:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');

/**
 * The DONE ready state for XmlHttpRequest
 *
 * Defining it here as a constant b/c XMLHttpRequest.DONE is not always defined
 * (e.g. during testing, it is `undefined`)
 *
 * @see {@link https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/readyState}
 */
const XHR_READYSTATE_DONE = 4;

/**
 * Creates a Transport that uses the XMLHttpRequest API to send events to Sentry.
 */
function makeXHRTransport(options) {
  function makeRequest(request) {
    return new utils.SyncPromise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.onerror = reject;

      xhr.onreadystatechange = () => {
        if (xhr.readyState === XHR_READYSTATE_DONE) {
          resolve({
            statusCode: xhr.status,
            headers: {
              'x-sentry-rate-limits': xhr.getResponseHeader('X-Sentry-Rate-Limits'),
              'retry-after': xhr.getResponseHeader('Retry-After'),
            },
          });
        }
      };

      xhr.open('POST', options.url);

      for (const header in options.headers) {
        if (Object.prototype.hasOwnProperty.call(options.headers, header)) {
          xhr.setRequestHeader(header, options.headers[header]);
        }
      }

      xhr.send(request.body);
    });
  }

  return core.createTransport(options, makeRequest);
}

exports.makeXHRTransport = makeXHRTransport;


},{"@sentry/core":24,"@sentry/utils":130}],19:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

const SENTRY_API_VERSION = '7';

/** Returns the prefix to construct Sentry ingestion API endpoints. */
function getBaseApiEndpoint(dsn) {
  const protocol = dsn.protocol ? `${dsn.protocol}:` : '';
  const port = dsn.port ? `:${dsn.port}` : '';
  return `${protocol}//${dsn.host}${port}${dsn.path ? `/${dsn.path}` : ''}/api/`;
}

/** Returns the ingest API endpoint for target. */
function _getIngestEndpoint(dsn) {
  return `${getBaseApiEndpoint(dsn)}${dsn.projectId}/envelope/`;
}

/** Returns a URL-encoded string with auth config suitable for a query string. */
function _encodedAuth(dsn, sdkInfo) {
  return utils.urlEncode({
    // We send only the minimum set of required information. See
    // https://github.com/getsentry/sentry-javascript/issues/2572.
    sentry_key: dsn.publicKey,
    sentry_version: SENTRY_API_VERSION,
    ...(sdkInfo && { sentry_client: `${sdkInfo.name}/${sdkInfo.version}` }),
  });
}

/**
 * Returns the envelope endpoint URL with auth in the query string.
 *
 * Sending auth as part of the query string and not as custom HTTP headers avoids CORS preflight requests.
 */
function getEnvelopeEndpointWithUrlEncodedAuth(
  dsn,
  // TODO (v8): Remove `tunnelOrOptions` in favor of `options`, and use the substitute code below
  // options: ClientOptions = {} as ClientOptions,
  tunnelOrOptions = {} ,
) {
  // TODO (v8): Use this code instead
  // const { tunnel, _metadata = {} } = options;
  // return tunnel ? tunnel : `${_getIngestEndpoint(dsn)}?${_encodedAuth(dsn, _metadata.sdk)}`;

  const tunnel = typeof tunnelOrOptions === 'string' ? tunnelOrOptions : tunnelOrOptions.tunnel;
  const sdkInfo =
    typeof tunnelOrOptions === 'string' || !tunnelOrOptions._metadata ? undefined : tunnelOrOptions._metadata.sdk;

  return tunnel ? tunnel : `${_getIngestEndpoint(dsn)}?${_encodedAuth(dsn, sdkInfo)}`;
}

/** Returns the url to the report dialog endpoint. */
function getReportDialogEndpoint(
  dsnLike,
  dialogOptions

,
) {
  const dsn = utils.makeDsn(dsnLike);
  const endpoint = `${getBaseApiEndpoint(dsn)}embed/error-page/`;

  let encodedOptions = `dsn=${utils.dsnToString(dsn)}`;
  for (const key in dialogOptions) {
    if (key === 'dsn') {
      continue;
    }

    if (key === 'user') {
      const user = dialogOptions.user;
      if (!user) {
        continue;
      }
      if (user.name) {
        encodedOptions += `&name=${encodeURIComponent(user.name)}`;
      }
      if (user.email) {
        encodedOptions += `&email=${encodeURIComponent(user.email)}`;
      }
    } else {
      encodedOptions += `&${encodeURIComponent(key)}=${encodeURIComponent(dialogOptions[key] )}`;
    }
  }

  return `${endpoint}?${encodedOptions}`;
}

exports.getEnvelopeEndpointWithUrlEncodedAuth = getEnvelopeEndpointWithUrlEncodedAuth;
exports.getReportDialogEndpoint = getReportDialogEndpoint;


},{"@sentry/utils":130}],20:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const api = require('./api.js');
const envelope = require('./envelope.js');
const integration = require('./integration.js');
const scope = require('./scope.js');
const session = require('./session.js');

const ALREADY_SEEN_ERROR = "Not capturing exception because it's already been captured.";

/**
 * Base implementation for all JavaScript SDK clients.
 *
 * Call the constructor with the corresponding options
 * specific to the client subclass. To access these options later, use
 * {@link Client.getOptions}.
 *
 * If a Dsn is specified in the options, it will be parsed and stored. Use
 * {@link Client.getDsn} to retrieve the Dsn at any moment. In case the Dsn is
 * invalid, the constructor will throw a {@link SentryException}. Note that
 * without a valid Dsn, the SDK will not send any events to Sentry.
 *
 * Before sending an event, it is passed through
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
 * class NodeClient extends BaseClient<NodeOptions> {
 *   public constructor(options: NodeOptions) {
 *     super(options);
 *   }
 *
 *   // ...
 * }
 */
class BaseClient {
  /** Options passed to the SDK. */

  /** The client Dsn, if specified in options. Without this Dsn, the SDK will be disabled. */

  /** Array of set up integrations. */
   __init() {this._integrations = {};}

  /** Indicates whether this client's integrations have been set up. */
   __init2() {this._integrationsInitialized = false;}

  /** Number of calls being processed */
   __init3() {this._numProcessing = 0;}

  /** Holds flushable  */
   __init4() {this._outcomes = {};}

  /**
   * Initializes this client instance.
   *
   * @param options Options for the client.
   */
   constructor(options) {;BaseClient.prototype.__init.call(this);BaseClient.prototype.__init2.call(this);BaseClient.prototype.__init3.call(this);BaseClient.prototype.__init4.call(this);
    this._options = options;
    if (options.dsn) {
      this._dsn = utils.makeDsn(options.dsn);
      const url = api.getEnvelopeEndpointWithUrlEncodedAuth(this._dsn, options);
      this._transport = options.transport({
        recordDroppedEvent: this.recordDroppedEvent.bind(this),
        ...options.transportOptions,
        url,
      });
    } else {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn('No DSN provided, client will not do anything.');
    }
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
   captureException(exception, hint, scope) {
    // ensure we haven't captured this very object before
    if (utils.checkOrSetAlreadyCaught(exception)) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log(ALREADY_SEEN_ERROR);
      return;
    }

    let eventId = hint && hint.event_id;

    this._process(
      this.eventFromException(exception, hint)
        .then(event => this._captureEvent(event, hint, scope))
        .then(result => {
          eventId = result;
        }),
    );

    return eventId;
  }

  /**
   * @inheritDoc
   */
   captureMessage(
    message,
    // eslint-disable-next-line deprecation/deprecation
    level,
    hint,
    scope,
  ) {
    let eventId = hint && hint.event_id;

    const promisedEvent = utils.isPrimitive(message)
      ? this.eventFromMessage(String(message), level, hint)
      : this.eventFromException(message, hint);

    this._process(
      promisedEvent
        .then(event => this._captureEvent(event, hint, scope))
        .then(result => {
          eventId = result;
        }),
    );

    return eventId;
  }

  /**
   * @inheritDoc
   */
   captureEvent(event, hint, scope) {
    // ensure we haven't captured this very object before
    if (hint && hint.originalException && utils.checkOrSetAlreadyCaught(hint.originalException)) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log(ALREADY_SEEN_ERROR);
      return;
    }

    let eventId = hint && hint.event_id;

    this._process(
      this._captureEvent(event, hint, scope).then(result => {
        eventId = result;
      }),
    );

    return eventId;
  }

  /**
   * @inheritDoc
   */
   captureSession(session$1) {
    if (!this._isEnabled()) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn('SDK not enabled, will not capture session.');
      return;
    }

    if (!(typeof session$1.release === 'string')) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn('Discarded session because of missing or non-string release');
    } else {
      this.sendSession(session$1);
      // After sending, we set init false to indicate it's not the first occurrence
      session.updateSession(session$1, { init: false });
    }
  }

  /**
   * @inheritDoc
   */
   getDsn() {
    return this._dsn;
  }

  /**
   * @inheritDoc
   */
   getOptions() {
    return this._options;
  }

  /**
   * @inheritDoc
   */
   getTransport() {
    return this._transport;
  }

  /**
   * @inheritDoc
   */
   flush(timeout) {
    const transport = this._transport;
    if (transport) {
      return this._isClientDoneProcessing(timeout).then(clientFinished => {
        return transport.flush(timeout).then(transportFlushed => clientFinished && transportFlushed);
      });
    } else {
      return utils.resolvedSyncPromise(true);
    }
  }

  /**
   * @inheritDoc
   */
   close(timeout) {
    return this.flush(timeout).then(result => {
      this.getOptions().enabled = false;
      return result;
    });
  }

  /**
   * Sets up the integrations
   */
   setupIntegrations() {
    if (this._isEnabled() && !this._integrationsInitialized) {
      this._integrations = integration.setupIntegrations(this._options.integrations);
      this._integrationsInitialized = true;
    }
  }

  /**
   * Gets an installed integration by its `id`.
   *
   * @returns The installed integration or `undefined` if no integration with that `id` was installed.
   */
   getIntegrationById(integrationId) {
    return this._integrations[integrationId];
  }

  /**
   * @inheritDoc
   */
   getIntegration(integration) {
    try {
      return (this._integrations[integration.id] ) || null;
    } catch (_oO) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn(`Cannot retrieve integration ${integration.id} from the current Client`);
      return null;
    }
  }

  /**
   * @inheritDoc
   */
   sendEvent(event, hint = {}) {
    if (this._dsn) {
      let env = envelope.createEventEnvelope(event, this._dsn, this._options._metadata, this._options.tunnel);

      for (const attachment of hint.attachments || []) {
        env = utils.addItemToEnvelope(
          env,
          utils.createAttachmentEnvelopeItem(
            attachment,
            this._options.transportOptions && this._options.transportOptions.textEncoder,
          ),
        );
      }

      this._sendEnvelope(env);
    }
  }

  /**
   * @inheritDoc
   */
   sendSession(session) {
    if (this._dsn) {
      const env = envelope.createSessionEnvelope(session, this._dsn, this._options._metadata, this._options.tunnel);
      this._sendEnvelope(env);
    }
  }

  /**
   * @inheritDoc
   */
   recordDroppedEvent(reason, category, _event) {
    // Note: we use `event` in replay, where we overwrite this hook.

    if (this._options.sendClientReports) {
      // We want to track each category (error, transaction, session) separately
      // but still keep the distinction between different type of outcomes.
      // We could use nested maps, but it's much easier to read and type this way.
      // A correct type for map-based implementation if we want to go that route
      // would be `Partial<Record<SentryRequestType, Partial<Record<Outcome, number>>>>`
      // With typescript 4.1 we could even use template literal types
      const key = `${reason}:${category}`;
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log(`Adding outcome: "${key}"`);

      // The following works because undefined + 1 === NaN and NaN is falsy
      this._outcomes[key] = this._outcomes[key] + 1 || 1;
    }
  }

  /** Updates existing session based on the provided event */
   _updateSessionFromEvent(session$1, event) {
    let crashed = false;
    let errored = false;
    const exceptions = event.exception && event.exception.values;

    if (exceptions) {
      errored = true;

      for (const ex of exceptions) {
        const mechanism = ex.mechanism;
        if (mechanism && mechanism.handled === false) {
          crashed = true;
          break;
        }
      }
    }

    // A session is updated and that session update is sent in only one of the two following scenarios:
    // 1. Session with non terminal status and 0 errors + an error occurred -> Will set error count to 1 and send update
    // 2. Session with non terminal status and 1 error + a crash occurred -> Will set status crashed and send update
    const sessionNonTerminal = session$1.status === 'ok';
    const shouldUpdateAndSend = (sessionNonTerminal && session$1.errors === 0) || (sessionNonTerminal && crashed);

    if (shouldUpdateAndSend) {
      session.updateSession(session$1, {
        ...(crashed && { status: 'crashed' }),
        errors: session$1.errors || Number(errored || crashed),
      });
      this.captureSession(session$1);
    }
  }

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
   _isClientDoneProcessing(timeout) {
    return new utils.SyncPromise(resolve => {
      let ticked = 0;
      const tick = 1;

      const interval = setInterval(() => {
        if (this._numProcessing == 0) {
          clearInterval(interval);
          resolve(true);
        } else {
          ticked += tick;
          if (timeout && ticked >= timeout) {
            clearInterval(interval);
            resolve(false);
          }
        }
      }, tick);
    });
  }

  /** Determines whether this SDK is enabled and a valid Dsn is present. */
   _isEnabled() {
    return this.getOptions().enabled !== false && this._dsn !== undefined;
  }

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
   _prepareEvent(event, hint, scope$1) {
    const { normalizeDepth = 3, normalizeMaxBreadth = 1000 } = this.getOptions();
    const prepared = {
      ...event,
      event_id: event.event_id || hint.event_id || utils.uuid4(),
      timestamp: event.timestamp || utils.dateTimestampInSeconds(),
    };

    this._applyClientOptions(prepared);
    this._applyIntegrationsMetadata(prepared);

    // If we have scope given to us, use it as the base for further modifications.
    // This allows us to prevent unnecessary copying of data if `captureContext` is not provided.
    let finalScope = scope$1;
    if (hint.captureContext) {
      finalScope = scope.Scope.clone(finalScope).update(hint.captureContext);
    }

    // We prepare the result here with a resolved Event.
    let result = utils.resolvedSyncPromise(prepared);

    // This should be the last thing called, since we want that
    // {@link Hub.addEventProcessor} gets the finished prepared event.
    //
    // We need to check for the existence of `finalScope.getAttachments`
    // because `getAttachments` can be undefined if users are using an older version
    // of `@sentry/core` that does not have the `getAttachments` method.
    // See: https://github.com/getsentry/sentry-javascript/issues/5229
    if (finalScope && finalScope.getAttachments) {
      // Collect attachments from the hint and scope
      const attachments = [...(hint.attachments || []), ...finalScope.getAttachments()];

      if (attachments.length) {
        hint.attachments = attachments;
      }

      // In case we have a hub we reassign it.
      result = finalScope.applyToEvent(prepared, hint);
    }

    return result.then(evt => {
      if (typeof normalizeDepth === 'number' && normalizeDepth > 0) {
        return this._normalizeEvent(evt, normalizeDepth, normalizeMaxBreadth);
      }
      return evt;
    });
  }

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
   _normalizeEvent(event, depth, maxBreadth) {
    if (!event) {
      return null;
    }

    const normalized = {
      ...event,
      ...(event.breadcrumbs && {
        breadcrumbs: event.breadcrumbs.map(b => ({
          ...b,
          ...(b.data && {
            data: utils.normalize(b.data, depth, maxBreadth),
          }),
        })),
      }),
      ...(event.user && {
        user: utils.normalize(event.user, depth, maxBreadth),
      }),
      ...(event.contexts && {
        contexts: utils.normalize(event.contexts, depth, maxBreadth),
      }),
      ...(event.extra && {
        extra: utils.normalize(event.extra, depth, maxBreadth),
      }),
    };

    // event.contexts.trace stores information about a Transaction. Similarly,
    // event.spans[] stores information about child Spans. Given that a
    // Transaction is conceptually a Span, normalization should apply to both
    // Transactions and Spans consistently.
    // For now the decision is to skip normalization of Transactions and Spans,
    // so this block overwrites the normalized event to add back the original
    // Transaction information prior to normalization.
    if (event.contexts && event.contexts.trace && normalized.contexts) {
      normalized.contexts.trace = event.contexts.trace;

      // event.contexts.trace.data may contain circular/dangerous data so we need to normalize it
      if (event.contexts.trace.data) {
        normalized.contexts.trace.data = utils.normalize(event.contexts.trace.data, depth, maxBreadth);
      }
    }

    // event.spans[].data may contain circular/dangerous data so we need to normalize it
    if (event.spans) {
      normalized.spans = event.spans.map(span => {
        // We cannot use the spread operator here because `toJSON` on `span` is non-enumerable
        if (span.data) {
          span.data = utils.normalize(span.data, depth, maxBreadth);
        }
        return span;
      });
    }

    return normalized;
  }

  /**
   *  Enhances event using the client configuration.
   *  It takes care of all "static" values like environment, release and `dist`,
   *  as well as truncating overly long values.
   * @param event event instance to be enhanced
   */
   _applyClientOptions(event) {
    const options = this.getOptions();
    const { environment, release, dist, maxValueLength = 250 } = options;

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
      event.message = utils.truncate(event.message, maxValueLength);
    }

    const exception = event.exception && event.exception.values && event.exception.values[0];
    if (exception && exception.value) {
      exception.value = utils.truncate(exception.value, maxValueLength);
    }

    const request = event.request;
    if (request && request.url) {
      request.url = utils.truncate(request.url, maxValueLength);
    }
  }

  /**
   * This function adds all used integrations to the SDK info in the event.
   * @param event The event that will be filled with all integrations.
   */
   _applyIntegrationsMetadata(event) {
    const integrationsArray = Object.keys(this._integrations);
    if (integrationsArray.length > 0) {
      event.sdk = event.sdk || {};
      event.sdk.integrations = [...(event.sdk.integrations || []), ...integrationsArray];
    }
  }

  /**
   * Processes the event and logs an error in case of rejection
   * @param event
   * @param hint
   * @param scope
   */
   _captureEvent(event, hint = {}, scope) {
    return this._processEvent(event, hint, scope).then(
      finalEvent => {
        return finalEvent.event_id;
      },
      reason => {
        if ((typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__)) {
          // If something's gone wrong, log the error as a warning. If it's just us having used a `SentryError` for
          // control flow, log just the message (no stack) as a log-level log.
          const sentryError = reason ;
          if (sentryError.logLevel === 'log') {
            utils.logger.log(sentryError.message);
          } else {
            utils.logger.warn(sentryError);
          }
        }
        return undefined;
      },
    );
  }

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
   _processEvent(event, hint, scope) {
    const options = this.getOptions();
    const { sampleRate } = options;

    if (!this._isEnabled()) {
      return utils.rejectedSyncPromise(new utils.SentryError('SDK not enabled, will not capture event.', 'log'));
    }

    const isTransaction = isTransactionEvent(event);
    const isError = isErrorEvent(event);
    const eventType = event.type || 'error';
    const beforeSendLabel = `before send for type \`${eventType}\``;

    // 1.0 === 100% events are sent
    // 0.0 === 0% events are sent
    // Sampling for transaction happens somewhere else
    if (isError && typeof sampleRate === 'number' && Math.random() > sampleRate) {
      this.recordDroppedEvent('sample_rate', 'error', event);
      return utils.rejectedSyncPromise(
        new utils.SentryError(
          `Discarding event because it's not included in the random sample (sampling rate = ${sampleRate})`,
          'log',
        ),
      );
    }

    return this._prepareEvent(event, hint, scope)
      .then(prepared => {
        if (prepared === null) {
          this.recordDroppedEvent('event_processor', eventType, event);
          throw new utils.SentryError('An event processor returned `null`, will not send event.', 'log');
        }

        const isInternalException = hint.data && (hint.data ).__sentry__ === true;
        if (isInternalException) {
          return prepared;
        }

        const result = processBeforeSend(options, prepared, hint);
        return _validateBeforeSendResult(result, beforeSendLabel);
      })
      .then(processedEvent => {
        if (processedEvent === null) {
          this.recordDroppedEvent('before_send', event.type || 'error', event);
          throw new utils.SentryError(`${beforeSendLabel} returned \`null\`, will not send event.`, 'log');
        }

        const session = scope && scope.getSession();
        if (!isTransaction && session) {
          this._updateSessionFromEvent(session, processedEvent);
        }

        // None of the Sentry built event processor will update transaction name,
        // so if the transaction name has been changed by an event processor, we know
        // it has to come from custom event processor added by a user
        const transactionInfo = processedEvent.transaction_info;
        if (isTransaction && transactionInfo && processedEvent.transaction !== event.transaction) {
          const source = 'custom';
          processedEvent.transaction_info = {
            ...transactionInfo,
            source,
            changes: [
              ...transactionInfo.changes,
              {
                source,
                // use the same timestamp as the processed event.
                timestamp: processedEvent.timestamp ,
                propagations: transactionInfo.propagations,
              },
            ],
          };
        }

        this.sendEvent(processedEvent, hint);
        return processedEvent;
      })
      .then(null, reason => {
        if (reason instanceof utils.SentryError) {
          throw reason;
        }

        this.captureException(reason, {
          data: {
            __sentry__: true,
          },
          originalException: reason ,
        });
        throw new utils.SentryError(
          `Event processing pipeline threw an error, original event will not be sent. Details have been sent as a new event.\nReason: ${reason}`,
        );
      });
  }

  /**
   * Occupies the client with processing and event
   */
   _process(promise) {
    this._numProcessing++;
    void promise.then(
      value => {
        this._numProcessing--;
        return value;
      },
      reason => {
        this._numProcessing--;
        return reason;
      },
    );
  }

  /**
   * @inheritdoc
   */
   _sendEnvelope(envelope) {
    if (this._transport && this._dsn) {
      this._transport.send(envelope).then(null, reason => {
        (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('Error while sending event:', reason);
      });
    } else {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('Transport disabled');
    }
  }

  /**
   * Clears outcomes on this client and returns them.
   */
   _clearOutcomes() {
    const outcomes = this._outcomes;
    this._outcomes = {};
    return Object.keys(outcomes).map(key => {
      const [reason, category] = key.split(':') ;
      return {
        reason,
        category,
        quantity: outcomes[key],
      };
    });
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types

}

/**
 * Verifies that return value of configured `beforeSend` or `beforeSendTransaction` is of expected type, and returns the value if so.
 */
function _validateBeforeSendResult(
  beforeSendResult,
  beforeSendLabel,
) {
  const invalidValueError = `${beforeSendLabel} must return \`null\` or a valid event.`;
  if (utils.isThenable(beforeSendResult)) {
    return beforeSendResult.then(
      event => {
        if (!utils.isPlainObject(event) && event !== null) {
          throw new utils.SentryError(invalidValueError);
        }
        return event;
      },
      e => {
        throw new utils.SentryError(`${beforeSendLabel} rejected with ${e}`);
      },
    );
  } else if (!utils.isPlainObject(beforeSendResult) && beforeSendResult !== null) {
    throw new utils.SentryError(invalidValueError);
  }
  return beforeSendResult;
}

/**
 * Process the matching `beforeSendXXX` callback.
 */
function processBeforeSend(
  options,
  event,
  hint,
) {
  const { beforeSend, beforeSendTransaction } = options;

  if (isErrorEvent(event) && beforeSend) {
    return beforeSend(event, hint);
  }

  if (isTransactionEvent(event) && beforeSendTransaction) {
    return beforeSendTransaction(event, hint);
  }

  return event;
}

function isErrorEvent(event) {
  return event.type === undefined;
}

function isTransactionEvent(event) {
  return event.type === 'transaction';
}

exports.BaseClient = BaseClient;


},{"./api.js":19,"./envelope.js":21,"./integration.js":25,"./scope.js":29,"./session.js":31,"@sentry/utils":130}],21:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

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
  event.sdk.integrations = [...(event.sdk.integrations || []), ...(sdkInfo.integrations || [])];
  event.sdk.packages = [...(event.sdk.packages || []), ...(sdkInfo.packages || [])];
  return event;
}

/** Creates an envelope from a Session */
function createSessionEnvelope(
  session,
  dsn,
  metadata,
  tunnel,
) {
  const sdkInfo = utils.getSdkMetadataForEnvelopeHeader(metadata);
  const envelopeHeaders = {
    sent_at: new Date().toISOString(),
    ...(sdkInfo && { sdk: sdkInfo }),
    ...(!!tunnel && { dsn: utils.dsnToString(dsn) }),
  };

  const envelopeItem =
    'aggregates' in session ? [{ type: 'sessions' }, session] : [{ type: 'session' }, session];

  return utils.createEnvelope(envelopeHeaders, [envelopeItem]);
}

/**
 * Create an Envelope from an event.
 */
function createEventEnvelope(
  event,
  dsn,
  metadata,
  tunnel,
) {
  const sdkInfo = utils.getSdkMetadataForEnvelopeHeader(metadata);
  const eventType = event.type || 'event';

  enhanceEventWithSdkInfo(event, metadata && metadata.sdk);

  const envelopeHeaders = utils.createEventEnvelopeHeaders(event, sdkInfo, tunnel, dsn);

  // Prevent this data (which, if it exists, was used in earlier steps in the processing pipeline) from being sent to
  // sentry. (Note: Our use of this property comes and goes with whatever we might be debugging, whatever hacks we may
  // have temporarily added, etc. Even if we don't happen to be using it at some point in the future, let's not get rid
  // of this `delete`, lest we miss putting it back in the next time the property is in use.)
  delete event.sdkProcessingMetadata;

  const eventItem = [{ type: eventType }, event];
  return utils.createEnvelope(envelopeHeaders, [eventItem]);
}

exports.createEventEnvelope = createEventEnvelope;
exports.createSessionEnvelope = createSessionEnvelope;


},{"@sentry/utils":130}],22:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const hub = require('./hub.js');

// Note: All functions in this file are typed with a return value of `ReturnType<Hub[HUB_FUNCTION]>`,
// where HUB_FUNCTION is some method on the Hub class.
//
// This is done to make sure the top level SDK methods stay in sync with the hub methods.
// Although every method here has an explicit return type, some of them (that map to void returns) do not
// contain `return` keywords. This is done to save on bundle size, as `return` is not minifiable.

/**
 * Captures an exception event and sends it to Sentry.
 *
 * @param exception An exception-like object.
 * @param captureContext Additional scope data to apply to exception event.
 * @returns The generated eventId.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
function captureException(exception, captureContext) {
  return hub.getCurrentHub().captureException(exception, { captureContext });
}

/**
 * Captures a message event and sends it to Sentry.
 *
 * @param message The message to send to Sentry.
 * @param Severity Define the level of the message.
 * @returns The generated eventId.
 */
function captureMessage(
  message,
  // eslint-disable-next-line deprecation/deprecation
  captureContext,
) {
  // This is necessary to provide explicit scopes upgrade, without changing the original
  // arity of the `captureMessage(message, level)` method.
  const level = typeof captureContext === 'string' ? captureContext : undefined;
  const context = typeof captureContext !== 'string' ? { captureContext } : undefined;
  return hub.getCurrentHub().captureMessage(message, level, context);
}

/**
 * Captures a manually created event and sends it to Sentry.
 *
 * @param event The event to send to Sentry.
 * @returns The generated eventId.
 */
function captureEvent(event, hint) {
  return hub.getCurrentHub().captureEvent(event, hint);
}

/**
 * Callback to set context information onto the scope.
 * @param callback Callback function that receives Scope.
 */
function configureScope(callback) {
  hub.getCurrentHub().configureScope(callback);
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
  hub.getCurrentHub().addBreadcrumb(breadcrumb);
}

/**
 * Sets context data with the given name.
 * @param name of the context
 * @param context Any kind of data. This data will be normalized.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function setContext(name, context) {
  hub.getCurrentHub().setContext(name, context);
}

/**
 * Set an object that will be merged sent as extra data with the event.
 * @param extras Extras object to merge into current context.
 */
function setExtras(extras) {
  hub.getCurrentHub().setExtras(extras);
}

/**
 * Set key:value that will be sent as extra data with the event.
 * @param key String of extra
 * @param extra Any kind of data. This data will be normalized.
 */
function setExtra(key, extra) {
  hub.getCurrentHub().setExtra(key, extra);
}

/**
 * Set an object that will be merged sent as tags data with the event.
 * @param tags Tags context object to merge into current context.
 */
function setTags(tags) {
  hub.getCurrentHub().setTags(tags);
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
  hub.getCurrentHub().setTag(key, value);
}

/**
 * Updates user context information for future events.
 *
 * @param user User context object to be set in the current context. Pass `null` to unset the user.
 */
function setUser(user) {
  hub.getCurrentHub().setUser(user);
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
  hub.getCurrentHub().withScope(callback);
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
 * NOTE: This function should only be used for *manual* instrumentation. Auto-instrumentation should call
 * `startTransaction` directly on the hub.
 *
 * @param context Properties of the new `Transaction`.
 * @param customSamplingContext Information given to the transaction sampling function (along with context-dependent
 * default values). See {@link Options.tracesSampler}.
 *
 * @returns The transaction which was just started
 */
function startTransaction(
  context,
  customSamplingContext,
) {
  return hub.getCurrentHub().startTransaction({ ...context }, customSamplingContext);
}

exports.addBreadcrumb = addBreadcrumb;
exports.captureEvent = captureEvent;
exports.captureException = captureException;
exports.captureMessage = captureMessage;
exports.configureScope = configureScope;
exports.setContext = setContext;
exports.setExtra = setExtra;
exports.setExtras = setExtras;
exports.setTag = setTag;
exports.setTags = setTags;
exports.setUser = setUser;
exports.startTransaction = startTransaction;
exports.withScope = withScope;


},{"./hub.js":23}],23:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const scope = require('./scope.js');
const session = require('./session.js');

/**
 * API compatibility version of this hub.
 *
 * WARNING: This number should only be increased when the global interface
 * changes and new methods are introduced.
 *
 * @hidden
 */
const API_VERSION = 4;

/**
 * Default maximum number of breadcrumbs added to an event. Can be overwritten
 * with {@link Options.maxBreadcrumbs}.
 */
const DEFAULT_BREADCRUMBS = 100;

/**
 * A layer in the process stack.
 * @hidden
 */

/**
 * @inheritDoc
 */
class Hub  {
  /** Is a {@link Layer}[] containing the client and scope */
    __init() {this._stack = [{}];}

  /** Contains the last event id of a captured event.  */

  /**
   * Creates a new instance of the hub, will push one {@link Layer} into the
   * internal stack on creation.
   *
   * @param client bound to the hub.
   * @param scope bound to the hub.
   * @param version number, higher number means higher priority.
   */
   constructor(client, scope$1 = new scope.Scope(),   _version = API_VERSION) {;this._version = _version;Hub.prototype.__init.call(this);
    this.getStackTop().scope = scope$1;
    if (client) {
      this.bindClient(client);
    }
  }

  /**
   * @inheritDoc
   */
   isOlderThan(version) {
    return this._version < version;
  }

  /**
   * @inheritDoc
   */
   bindClient(client) {
    const top = this.getStackTop();
    top.client = client;
    if (client && client.setupIntegrations) {
      client.setupIntegrations();
    }
  }

  /**
   * @inheritDoc
   */
   pushScope() {
    // We want to clone the content of prev scope
    const scope$1 = scope.Scope.clone(this.getScope());
    this.getStack().push({
      client: this.getClient(),
      scope: scope$1,
    });
    return scope$1;
  }

  /**
   * @inheritDoc
   */
   popScope() {
    if (this.getStack().length <= 1) return false;
    return !!this.getStack().pop();
  }

  /**
   * @inheritDoc
   */
   withScope(callback) {
    const scope = this.pushScope();
    try {
      callback(scope);
    } finally {
      this.popScope();
    }
  }

  /**
   * @inheritDoc
   */
   getClient() {
    return this.getStackTop().client ;
  }

  /** Returns the scope of the top stack. */
   getScope() {
    return this.getStackTop().scope;
  }

  /** Returns the scope stack for domains or the process. */
   getStack() {
    return this._stack;
  }

  /** Returns the topmost scope layer in the order domain > local > process. */
   getStackTop() {
    return this._stack[this._stack.length - 1];
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
   captureException(exception, hint) {
    const eventId = (this._lastEventId = hint && hint.event_id ? hint.event_id : utils.uuid4());
    const syntheticException = new Error('Sentry syntheticException');
    this._withClient((client, scope) => {
      client.captureException(
        exception,
        {
          originalException: exception,
          syntheticException,
          ...hint,
          event_id: eventId,
        },
        scope,
      );
    });
    return eventId;
  }

  /**
   * @inheritDoc
   */
   captureMessage(
    message,
    // eslint-disable-next-line deprecation/deprecation
    level,
    hint,
  ) {
    const eventId = (this._lastEventId = hint && hint.event_id ? hint.event_id : utils.uuid4());
    const syntheticException = new Error(message);
    this._withClient((client, scope) => {
      client.captureMessage(
        message,
        level,
        {
          originalException: message,
          syntheticException,
          ...hint,
          event_id: eventId,
        },
        scope,
      );
    });
    return eventId;
  }

  /**
   * @inheritDoc
   */
   captureEvent(event, hint) {
    const eventId = hint && hint.event_id ? hint.event_id : utils.uuid4();
    if (event.type !== 'transaction') {
      this._lastEventId = eventId;
    }

    this._withClient((client, scope) => {
      client.captureEvent(event, { ...hint, event_id: eventId }, scope);
    });
    return eventId;
  }

  /**
   * @inheritDoc
   */
   lastEventId() {
    return this._lastEventId;
  }

  /**
   * @inheritDoc
   */
   addBreadcrumb(breadcrumb, hint) {
    const { scope, client } = this.getStackTop();

    if (!scope || !client) return;

    // eslint-disable-next-line @typescript-eslint/unbound-method
    const { beforeBreadcrumb = null, maxBreadcrumbs = DEFAULT_BREADCRUMBS } =
      (client.getOptions && client.getOptions()) || {};

    if (maxBreadcrumbs <= 0) return;

    const timestamp = utils.dateTimestampInSeconds();
    const mergedBreadcrumb = { timestamp, ...breadcrumb };
    const finalBreadcrumb = beforeBreadcrumb
      ? (utils.consoleSandbox(() => beforeBreadcrumb(mergedBreadcrumb, hint)) )
      : mergedBreadcrumb;

    if (finalBreadcrumb === null) return;

    scope.addBreadcrumb(finalBreadcrumb, maxBreadcrumbs);
  }

  /**
   * @inheritDoc
   */
   setUser(user) {
    const scope = this.getScope();
    if (scope) scope.setUser(user);
  }

  /**
   * @inheritDoc
   */
   setTags(tags) {
    const scope = this.getScope();
    if (scope) scope.setTags(tags);
  }

  /**
   * @inheritDoc
   */
   setExtras(extras) {
    const scope = this.getScope();
    if (scope) scope.setExtras(extras);
  }

  /**
   * @inheritDoc
   */
   setTag(key, value) {
    const scope = this.getScope();
    if (scope) scope.setTag(key, value);
  }

  /**
   * @inheritDoc
   */
   setExtra(key, extra) {
    const scope = this.getScope();
    if (scope) scope.setExtra(key, extra);
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
   setContext(name, context) {
    const scope = this.getScope();
    if (scope) scope.setContext(name, context);
  }

  /**
   * @inheritDoc
   */
   configureScope(callback) {
    const { scope, client } = this.getStackTop();
    if (scope && client) {
      callback(scope);
    }
  }

  /**
   * @inheritDoc
   */
   run(callback) {
    const oldHub = makeMain(this);
    try {
      callback(this);
    } finally {
      makeMain(oldHub);
    }
  }

  /**
   * @inheritDoc
   */
   getIntegration(integration) {
    const client = this.getClient();
    if (!client) return null;
    try {
      return client.getIntegration(integration);
    } catch (_oO) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn(`Cannot retrieve integration ${integration.id} from the current Hub`);
      return null;
    }
  }

  /**
   * @inheritDoc
   */
   startTransaction(context, customSamplingContext) {
    return this._callExtensionMethod('startTransaction', context, customSamplingContext);
  }

  /**
   * @inheritDoc
   */
   traceHeaders() {
    return this._callExtensionMethod('traceHeaders');
  }

  /**
   * @inheritDoc
   */
   captureSession(endSession = false) {
    // both send the update and pull the session from the scope
    if (endSession) {
      return this.endSession();
    }

    // only send the update
    this._sendSessionUpdate();
  }

  /**
   * @inheritDoc
   */
   endSession() {
    const layer = this.getStackTop();
    const scope = layer && layer.scope;
    const session$1 = scope && scope.getSession();
    if (session$1) {
      session.closeSession(session$1);
    }
    this._sendSessionUpdate();

    // the session is over; take it off of the scope
    if (scope) {
      scope.setSession();
    }
  }

  /**
   * @inheritDoc
   */
   startSession(context) {
    const { scope, client } = this.getStackTop();
    const { release, environment } = (client && client.getOptions()) || {};

    // Will fetch userAgent if called from browser sdk
    const { userAgent } = utils.GLOBAL_OBJ.navigator || {};

    const session$1 = session.makeSession({
      release,
      environment,
      ...(scope && { user: scope.getUser() }),
      ...(userAgent && { userAgent }),
      ...context,
    });

    if (scope) {
      // End existing session if there's one
      const currentSession = scope.getSession && scope.getSession();
      if (currentSession && currentSession.status === 'ok') {
        session.updateSession(currentSession, { status: 'exited' });
      }
      this.endSession();

      // Afterwards we set the new session on the scope
      scope.setSession(session$1);
    }

    return session$1;
  }

  /**
   * Returns if default PII should be sent to Sentry and propagated in ourgoing requests
   * when Tracing is used.
   */
   shouldSendDefaultPii() {
    const client = this.getClient();
    const options = client && client.getOptions();
    return Boolean(options && options.sendDefaultPii);
  }

  /**
   * Sends the current Session on the scope
   */
   _sendSessionUpdate() {
    const { scope, client } = this.getStackTop();
    if (!scope) return;

    const session = scope.getSession();
    if (session) {
      if (client && client.captureSession) {
        client.captureSession(session);
      }
    }
  }

  /**
   * Internal helper function to call a method on the top client if it exists.
   *
   * @param method The method to call on the client.
   * @param args Arguments to pass to the client function.
   */
   _withClient(callback) {
    const { scope, client } = this.getStackTop();
    if (client) {
      callback(client, scope);
    }
  }

  /**
   * Calls global extension method and binding current instance to the function call
   */
  // @ts-ignore Function lacks ending return statement and return type does not include 'undefined'. ts(2366)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
   _callExtensionMethod(method, ...args) {
    const carrier = getMainCarrier();
    const sentry = carrier.__SENTRY__;
    if (sentry && sentry.extensions && typeof sentry.extensions[method] === 'function') {
      return sentry.extensions[method].apply(this, args);
    }
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn(`Extension method ${method} couldn't be found, doing nothing.`);
  }
}

/**
 * Returns the global shim registry.
 *
 * FIXME: This function is problematic, because despite always returning a valid Carrier,
 * it has an optional `__SENTRY__` property, which then in turn requires us to always perform an unnecessary check
 * at the call-site. We always access the carrier through this function, so we can guarantee that `__SENTRY__` is there.
 **/
function getMainCarrier() {
  utils.GLOBAL_OBJ.__SENTRY__ = utils.GLOBAL_OBJ.__SENTRY__ || {
    extensions: {},
    hub: undefined,
  };
  return utils.GLOBAL_OBJ;
}

/**
 * Replaces the current main hub with the passed one on the global object
 *
 * @returns The old replaced hub
 */
function makeMain(hub) {
  const registry = getMainCarrier();
  const oldHub = getHubFromCarrier(registry);
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
  const registry = getMainCarrier();

  // If there's no hub, or its an old API, assign a new one
  if (!hasHubOnCarrier(registry) || getHubFromCarrier(registry).isOlderThan(API_VERSION)) {
    setHubOnCarrier(registry, new Hub());
  }

  // Prefer domains over global if they are there (applicable only to Node environment)
  if (utils.isNodeEnv()) {
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
  try {
    const sentry = getMainCarrier().__SENTRY__;
    const activeDomain = sentry && sentry.extensions && sentry.extensions.domain && sentry.extensions.domain.active;

    // If there's no active domain, just return global hub
    if (!activeDomain) {
      return getHubFromCarrier(registry);
    }

    // If there's no hub on current domain, or it's an old API, assign a new one
    if (!hasHubOnCarrier(activeDomain) || getHubFromCarrier(activeDomain).isOlderThan(API_VERSION)) {
      const registryHubTopStack = getHubFromCarrier(registry).getStackTop();
      setHubOnCarrier(activeDomain, new Hub(registryHubTopStack.client, scope.Scope.clone(registryHubTopStack.scope)));
    }

    // Return hub that lives on a domain
    return getHubFromCarrier(activeDomain);
  } catch (_Oo) {
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
  return utils.getGlobalSingleton('hub', () => new Hub(), carrier);
}

/**
 * This will set passed {@link Hub} on the passed object's __SENTRY__.hub attribute
 * @param carrier object
 * @param hub Hub
 * @returns A boolean indicating success or failure
 */
function setHubOnCarrier(carrier, hub) {
  if (!carrier) return false;
  const __SENTRY__ = (carrier.__SENTRY__ = carrier.__SENTRY__ || {});
  __SENTRY__.hub = hub;
  return true;
}

exports.API_VERSION = API_VERSION;
exports.Hub = Hub;
exports.getCurrentHub = getCurrentHub;
exports.getHubFromCarrier = getHubFromCarrier;
exports.getMainCarrier = getMainCarrier;
exports.makeMain = makeMain;
exports.setHubOnCarrier = setHubOnCarrier;


},{"./scope.js":29,"./session.js":31,"@sentry/utils":130}],24:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const exports$1 = require('./exports.js');
const hub = require('./hub.js');
const session = require('./session.js');
const sessionflusher = require('./sessionflusher.js');
const scope = require('./scope.js');
const api = require('./api.js');
const baseclient = require('./baseclient.js');
const sdk = require('./sdk.js');
const base = require('./transports/base.js');
const version = require('./version.js');
const integration = require('./integration.js');
const index = require('./integrations/index.js');
const functiontostring = require('./integrations/functiontostring.js');
const inboundfilters = require('./integrations/inboundfilters.js');

;
;

exports.addBreadcrumb = exports$1.addBreadcrumb;
exports.captureEvent = exports$1.captureEvent;
exports.captureException = exports$1.captureException;
exports.captureMessage = exports$1.captureMessage;
exports.configureScope = exports$1.configureScope;
exports.setContext = exports$1.setContext;
exports.setExtra = exports$1.setExtra;
exports.setExtras = exports$1.setExtras;
exports.setTag = exports$1.setTag;
exports.setTags = exports$1.setTags;
exports.setUser = exports$1.setUser;
exports.startTransaction = exports$1.startTransaction;
exports.withScope = exports$1.withScope;
exports.Hub = hub.Hub;
exports.getCurrentHub = hub.getCurrentHub;
exports.getHubFromCarrier = hub.getHubFromCarrier;
exports.getMainCarrier = hub.getMainCarrier;
exports.makeMain = hub.makeMain;
exports.setHubOnCarrier = hub.setHubOnCarrier;
exports.closeSession = session.closeSession;
exports.makeSession = session.makeSession;
exports.updateSession = session.updateSession;
exports.SessionFlusher = sessionflusher.SessionFlusher;
exports.Scope = scope.Scope;
exports.addGlobalEventProcessor = scope.addGlobalEventProcessor;
exports.getEnvelopeEndpointWithUrlEncodedAuth = api.getEnvelopeEndpointWithUrlEncodedAuth;
exports.getReportDialogEndpoint = api.getReportDialogEndpoint;
exports.BaseClient = baseclient.BaseClient;
exports.initAndBind = sdk.initAndBind;
exports.createTransport = base.createTransport;
exports.SDK_VERSION = version.SDK_VERSION;
exports.getIntegrationsToSetup = integration.getIntegrationsToSetup;
exports.Integrations = index;
exports.FunctionToString = functiontostring.FunctionToString;
exports.InboundFilters = inboundfilters.InboundFilters;


},{"./api.js":19,"./baseclient.js":20,"./exports.js":22,"./hub.js":23,"./integration.js":25,"./integrations/functiontostring.js":26,"./integrations/inboundfilters.js":27,"./integrations/index.js":28,"./scope.js":29,"./sdk.js":30,"./session.js":31,"./sessionflusher.js":32,"./transports/base.js":33,"./version.js":34}],25:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const hub = require('./hub.js');
const scope = require('./scope.js');

const installedIntegrations = [];

/** Map of integrations assigned to a client */

/**
 * Remove duplicates from the given array, preferring the last instance of any duplicate. Not guaranteed to
 * preseve the order of integrations in the array.
 *
 * @private
 */
function filterDuplicates(integrations) {
  const integrationsByName = {};

  integrations.forEach(currentInstance => {
    const { name } = currentInstance;

    const existingInstance = integrationsByName[name];

    // We want integrations later in the array to overwrite earlier ones of the same type, except that we never want a
    // default instance to overwrite an existing user instance
    if (existingInstance && !existingInstance.isDefaultInstance && currentInstance.isDefaultInstance) {
      return;
    }

    integrationsByName[name] = currentInstance;
  });

  return Object.values(integrationsByName);
}

/** Gets integrations to install */
function getIntegrationsToSetup(options) {
  const defaultIntegrations = options.defaultIntegrations || [];
  const userIntegrations = options.integrations;

  // We flag default instances, so that later we can tell them apart from any user-created instances of the same class
  defaultIntegrations.forEach(integration => {
    integration.isDefaultInstance = true;
  });

  let integrations;

  if (Array.isArray(userIntegrations)) {
    integrations = [...defaultIntegrations, ...userIntegrations];
  } else if (typeof userIntegrations === 'function') {
    integrations = utils.arrayify(userIntegrations(defaultIntegrations));
  } else {
    integrations = defaultIntegrations;
  }

  const finalIntegrations = filterDuplicates(integrations);

  // The `Debug` integration prints copies of the `event` and `hint` which will be passed to `beforeSend` or
  // `beforeSendTransaction`. It therefore has to run after all other integrations, so that the changes of all event
  // processors will be reflected in the printed values. For lack of a more elegant way to guarantee that, we therefore
  // locate it and, assuming it exists, pop it out of its current spot and shove it onto the end of the array.
  const debugIndex = finalIntegrations.findIndex(integration => integration.name === 'Debug');
  if (debugIndex !== -1) {
    const [debugInstance] = finalIntegrations.splice(debugIndex, 1);
    finalIntegrations.push(debugInstance);
  }

  return finalIntegrations;
}

/**
 * Given a list of integration instances this installs them all. When `withDefaults` is set to `true` then all default
 * integrations are added unless they were already provided before.
 * @param integrations array of integration instances
 * @param withDefault should enable default integrations
 */
function setupIntegrations(integrations) {
  const integrationIndex = {};

  integrations.forEach(integration => {
    integrationIndex[integration.name] = integration;

    if (installedIntegrations.indexOf(integration.name) === -1) {
      integration.setupOnce(scope.addGlobalEventProcessor, hub.getCurrentHub);
      installedIntegrations.push(integration.name);
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log(`Integration installed: ${integration.name}`);
    }
  });

  return integrationIndex;
}

exports.getIntegrationsToSetup = getIntegrationsToSetup;
exports.installedIntegrations = installedIntegrations;
exports.setupIntegrations = setupIntegrations;


},{"./hub.js":23,"./scope.js":29,"@sentry/utils":130}],26:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

let originalFunctionToString;

/** Patch toString calls to return proper name for wrapped functions */
class FunctionToString  {constructor() { FunctionToString.prototype.__init.call(this); }
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'FunctionToString';}

  /**
   * @inheritDoc
   */
   __init() {this.name = FunctionToString.id;}

  /**
   * @inheritDoc
   */
   setupOnce() {
    // eslint-disable-next-line @typescript-eslint/unbound-method
    originalFunctionToString = Function.prototype.toString;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Function.prototype.toString = function ( ...args) {
      const context = utils.getOriginalFunction(this) || this;
      return originalFunctionToString.apply(context, args);
    };
  }
} FunctionToString.__initStatic();

exports.FunctionToString = FunctionToString;


},{"@sentry/utils":130}],27:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

// "Script error." is hard coded into browsers for errors that it can't read.
// this is the result of a script being pulled in from an external domain and CORS.
const DEFAULT_IGNORE_ERRORS = [/^Script error\.?$/, /^Javascript error: Script error\.? on line 0$/];

/** Options for the InboundFilters integration */

/** Inbound filters configurable by the user */
class InboundFilters  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'InboundFilters';}

  /**
   * @inheritDoc
   */
   __init() {this.name = InboundFilters.id;}

   constructor(  _options = {}) {;this._options = _options;InboundFilters.prototype.__init.call(this);}

  /**
   * @inheritDoc
   */
   setupOnce(addGlobalEventProcessor, getCurrentHub) {
    const eventProcess = (event) => {
      const hub = getCurrentHub();
      if (hub) {
        const self = hub.getIntegration(InboundFilters);
        if (self) {
          const client = hub.getClient();
          const clientOptions = client ? client.getOptions() : {};
          const options = _mergeOptions(self._options, clientOptions);
          return _shouldDropEvent(event, options) ? null : event;
        }
      }
      return event;
    };

    eventProcess.id = this.name;
    addGlobalEventProcessor(eventProcess);
  }
} InboundFilters.__initStatic();

/** JSDoc */
function _mergeOptions(
  internalOptions = {},
  clientOptions = {},
) {
  return {
    allowUrls: [...(internalOptions.allowUrls || []), ...(clientOptions.allowUrls || [])],
    denyUrls: [...(internalOptions.denyUrls || []), ...(clientOptions.denyUrls || [])],
    ignoreErrors: [
      ...(internalOptions.ignoreErrors || []),
      ...(clientOptions.ignoreErrors || []),
      ...DEFAULT_IGNORE_ERRORS,
    ],
    ignoreInternal: internalOptions.ignoreInternal !== undefined ? internalOptions.ignoreInternal : true,
  };
}

/** JSDoc */
function _shouldDropEvent(event, options) {
  if (options.ignoreInternal && _isSentryError(event)) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
      utils.logger.warn(`Event dropped due to being internal Sentry Error.\nEvent: ${utils.getEventDescription(event)}`);
    return true;
  }
  if (_isIgnoredError(event, options.ignoreErrors)) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
      utils.logger.warn(
        `Event dropped due to being matched by \`ignoreErrors\` option.\nEvent: ${utils.getEventDescription(event)}`,
      );
    return true;
  }
  if (_isDeniedUrl(event, options.denyUrls)) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
      utils.logger.warn(
        `Event dropped due to being matched by \`denyUrls\` option.\nEvent: ${utils.getEventDescription(
          event,
        )}.\nUrl: ${_getEventFilterUrl(event)}`,
      );
    return true;
  }
  if (!_isAllowedUrl(event, options.allowUrls)) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
      utils.logger.warn(
        `Event dropped due to not being matched by \`allowUrls\` option.\nEvent: ${utils.getEventDescription(
          event,
        )}.\nUrl: ${_getEventFilterUrl(event)}`,
      );
    return true;
  }
  return false;
}

function _isIgnoredError(event, ignoreErrors) {
  if (!ignoreErrors || !ignoreErrors.length) {
    return false;
  }

  return _getPossibleEventMessages(event).some(message => utils.stringMatchesSomePattern(message, ignoreErrors));
}

function _isDeniedUrl(event, denyUrls) {
  // TODO: Use Glob instead?
  if (!denyUrls || !denyUrls.length) {
    return false;
  }
  const url = _getEventFilterUrl(event);
  return !url ? false : utils.stringMatchesSomePattern(url, denyUrls);
}

function _isAllowedUrl(event, allowUrls) {
  // TODO: Use Glob instead?
  if (!allowUrls || !allowUrls.length) {
    return true;
  }
  const url = _getEventFilterUrl(event);
  return !url ? true : utils.stringMatchesSomePattern(url, allowUrls);
}

function _getPossibleEventMessages(event) {
  if (event.message) {
    return [event.message];
  }
  if (event.exception) {
    try {
      const { type = '', value = '' } = (event.exception.values && event.exception.values[0]) || {};
      return [`${value}`, `${type}: ${value}`];
    } catch (oO) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error(`Cannot extract message for event ${utils.getEventDescription(event)}`);
      return [];
    }
  }
  return [];
}

function _isSentryError(event) {
  try {
    // @ts-ignore can't be a sentry error if undefined
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    return event.exception.values[0].type === 'SentryError';
  } catch (e) {
    // ignore
  }
  return false;
}

function _getLastValidUrl(frames = []) {
  for (let i = frames.length - 1; i >= 0; i--) {
    const frame = frames[i];

    if (frame && frame.filename !== '<anonymous>' && frame.filename !== '[native code]') {
      return frame.filename || null;
    }
  }

  return null;
}

function _getEventFilterUrl(event) {
  try {
    let frames;
    try {
      // @ts-ignore we only care about frames if the whole thing here is defined
      frames = event.exception.values[0].stacktrace.frames;
    } catch (e) {
      // ignore
    }
    return frames ? _getLastValidUrl(frames) : null;
  } catch (oO) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error(`Cannot extract url for event ${utils.getEventDescription(event)}`);
    return null;
  }
}

exports.InboundFilters = InboundFilters;
exports._mergeOptions = _mergeOptions;
exports._shouldDropEvent = _shouldDropEvent;


},{"@sentry/utils":130}],28:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const functiontostring = require('./functiontostring.js');
const inboundfilters = require('./inboundfilters.js');



exports.FunctionToString = functiontostring.FunctionToString;
exports.InboundFilters = inboundfilters.InboundFilters;


},{"./functiontostring.js":26,"./inboundfilters.js":27}],29:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const session = require('./session.js');

/**
 * Default value for maximum number of breadcrumbs added to an event.
 */
const DEFAULT_MAX_BREADCRUMBS = 100;

/**
 * Holds additional event information. {@link Scope.applyToEvent} will be
 * called by the client before an event will be sent.
 */
class Scope  {
  /** Flag if notifying is happening. */

  /** Callback for client to receive scope changes. */

  /** Callback list that will be called after {@link applyToEvent}. */

  /** Array of breadcrumbs. */

  /** User */

  /** Tags */

  /** Extra */

  /** Contexts */

  /** Attachments */

  /**
   * A place to stash data which is needed at some point in the SDK's event processing pipeline but which shouldn't get
   * sent to Sentry
   */

  /** Fingerprint */

  /** Severity */
  // eslint-disable-next-line deprecation/deprecation

  /** Transaction Name */

  /** Span */

  /** Session */

  /** Request Mode Session Status */

  // NOTE: Any field which gets added here should get added not only to the constructor but also to the `clone` method.

   constructor() {
    this._notifyingListeners = false;
    this._scopeListeners = [];
    this._eventProcessors = [];
    this._breadcrumbs = [];
    this._attachments = [];
    this._user = {};
    this._tags = {};
    this._extra = {};
    this._contexts = {};
    this._sdkProcessingMetadata = {};
  }

  /**
   * Inherit values from the parent scope.
   * @param scope to clone.
   */
   static clone(scope) {
    const newScope = new Scope();
    if (scope) {
      newScope._breadcrumbs = [...scope._breadcrumbs];
      newScope._tags = { ...scope._tags };
      newScope._extra = { ...scope._extra };
      newScope._contexts = { ...scope._contexts };
      newScope._user = scope._user;
      newScope._level = scope._level;
      newScope._span = scope._span;
      newScope._session = scope._session;
      newScope._transactionName = scope._transactionName;
      newScope._fingerprint = scope._fingerprint;
      newScope._eventProcessors = [...scope._eventProcessors];
      newScope._requestSession = scope._requestSession;
      newScope._attachments = [...scope._attachments];
      newScope._sdkProcessingMetadata = { ...scope._sdkProcessingMetadata };
    }
    return newScope;
  }

  /**
   * Add internal on change listener. Used for sub SDKs that need to store the scope.
   * @hidden
   */
   addScopeListener(callback) {
    this._scopeListeners.push(callback);
  }

  /**
   * @inheritDoc
   */
   addEventProcessor(callback) {
    this._eventProcessors.push(callback);
    return this;
  }

  /**
   * @inheritDoc
   */
   setUser(user) {
    this._user = user || {};
    if (this._session) {
      session.updateSession(this._session, { user });
    }
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   getUser() {
    return this._user;
  }

  /**
   * @inheritDoc
   */
   getRequestSession() {
    return this._requestSession;
  }

  /**
   * @inheritDoc
   */
   setRequestSession(requestSession) {
    this._requestSession = requestSession;
    return this;
  }

  /**
   * @inheritDoc
   */
   setTags(tags) {
    this._tags = {
      ...this._tags,
      ...tags,
    };
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setTag(key, value) {
    this._tags = { ...this._tags, [key]: value };
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setExtras(extras) {
    this._extra = {
      ...this._extra,
      ...extras,
    };
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setExtra(key, extra) {
    this._extra = { ...this._extra, [key]: extra };
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setFingerprint(fingerprint) {
    this._fingerprint = fingerprint;
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setLevel(
    // eslint-disable-next-line deprecation/deprecation
    level,
  ) {
    this._level = level;
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setTransactionName(name) {
    this._transactionName = name;
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setContext(key, context) {
    if (context === null) {
      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
      delete this._contexts[key];
    } else {
      this._contexts[key] = context;
    }

    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   setSpan(span) {
    this._span = span;
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   getSpan() {
    return this._span;
  }

  /**
   * @inheritDoc
   */
   getTransaction() {
    // Often, this span (if it exists at all) will be a transaction, but it's not guaranteed to be. Regardless, it will
    // have a pointer to the currently-active transaction.
    const span = this.getSpan();
    return span && span.transaction;
  }

  /**
   * @inheritDoc
   */
   setSession(session) {
    if (!session) {
      delete this._session;
    } else {
      this._session = session;
    }
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   getSession() {
    return this._session;
  }

  /**
   * @inheritDoc
   */
   update(captureContext) {
    if (!captureContext) {
      return this;
    }

    if (typeof captureContext === 'function') {
      const updatedScope = (captureContext )(this);
      return updatedScope instanceof Scope ? updatedScope : this;
    }

    if (captureContext instanceof Scope) {
      this._tags = { ...this._tags, ...captureContext._tags };
      this._extra = { ...this._extra, ...captureContext._extra };
      this._contexts = { ...this._contexts, ...captureContext._contexts };
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
    } else if (utils.isPlainObject(captureContext)) {
      // eslint-disable-next-line no-param-reassign
      captureContext = captureContext ;
      this._tags = { ...this._tags, ...captureContext.tags };
      this._extra = { ...this._extra, ...captureContext.extra };
      this._contexts = { ...this._contexts, ...captureContext.contexts };
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
  }

  /**
   * @inheritDoc
   */
   clear() {
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
    this._attachments = [];
    return this;
  }

  /**
   * @inheritDoc
   */
   addBreadcrumb(breadcrumb, maxBreadcrumbs) {
    const maxCrumbs = typeof maxBreadcrumbs === 'number' ? maxBreadcrumbs : DEFAULT_MAX_BREADCRUMBS;

    // No data has been changed, so don't notify scope listeners
    if (maxCrumbs <= 0) {
      return this;
    }

    const mergedBreadcrumb = {
      timestamp: utils.dateTimestampInSeconds(),
      ...breadcrumb,
    };
    this._breadcrumbs = [...this._breadcrumbs, mergedBreadcrumb].slice(-maxCrumbs);
    this._notifyScopeListeners();

    return this;
  }

  /**
   * @inheritDoc
   */
   getLastBreadcrumb() {
    return this._breadcrumbs[this._breadcrumbs.length - 1];
  }

  /**
   * @inheritDoc
   */
   clearBreadcrumbs() {
    this._breadcrumbs = [];
    this._notifyScopeListeners();
    return this;
  }

  /**
   * @inheritDoc
   */
   addAttachment(attachment) {
    this._attachments.push(attachment);
    return this;
  }

  /**
   * @inheritDoc
   */
   getAttachments() {
    return this._attachments;
  }

  /**
   * @inheritDoc
   */
   clearAttachments() {
    this._attachments = [];
    return this;
  }

  /**
   * Applies data from the scope to the event and runs all event processors on it.
   *
   * @param event Event
   * @param hint Object containing additional information about the original exception, for use by the event processors.
   * @hidden
   */
   applyToEvent(event, hint = {}) {
    if (this._extra && Object.keys(this._extra).length) {
      event.extra = { ...this._extra, ...event.extra };
    }
    if (this._tags && Object.keys(this._tags).length) {
      event.tags = { ...this._tags, ...event.tags };
    }
    if (this._user && Object.keys(this._user).length) {
      event.user = { ...this._user, ...event.user };
    }
    if (this._contexts && Object.keys(this._contexts).length) {
      event.contexts = { ...this._contexts, ...event.contexts };
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
      event.contexts = { trace: this._span.getTraceContext(), ...event.contexts };
      const transactionName = this._span.transaction && this._span.transaction.name;
      if (transactionName) {
        event.tags = { transaction: transactionName, ...event.tags };
      }
    }

    this._applyFingerprint(event);

    event.breadcrumbs = [...(event.breadcrumbs || []), ...this._breadcrumbs];
    event.breadcrumbs = event.breadcrumbs.length > 0 ? event.breadcrumbs : undefined;

    event.sdkProcessingMetadata = { ...event.sdkProcessingMetadata, ...this._sdkProcessingMetadata };

    return this._notifyEventProcessors([...getGlobalEventProcessors(), ...this._eventProcessors], event, hint);
  }

  /**
   * Add data which will be accessible during event processing but won't get sent to Sentry
   */
   setSDKProcessingMetadata(newData) {
    this._sdkProcessingMetadata = { ...this._sdkProcessingMetadata, ...newData };

    return this;
  }

  /**
   * This will be called after {@link applyToEvent} is finished.
   */
   _notifyEventProcessors(
    processors,
    event,
    hint,
    index = 0,
  ) {
    return new utils.SyncPromise((resolve, reject) => {
      const processor = processors[index];
      if (event === null || typeof processor !== 'function') {
        resolve(event);
      } else {
        const result = processor({ ...event }, hint) ;

        (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
          processor.id &&
          result === null &&
          utils.logger.log(`Event processor "${processor.id}" dropped event`);

        if (utils.isThenable(result)) {
          void result
            .then(final => this._notifyEventProcessors(processors, final, hint, index + 1).then(resolve))
            .then(null, reject);
        } else {
          void this._notifyEventProcessors(processors, result, hint, index + 1)
            .then(resolve)
            .then(null, reject);
        }
      }
    });
  }

  /**
   * This will be called on every set call.
   */
   _notifyScopeListeners() {
    // We need this check for this._notifyingListeners to be able to work on scope during updates
    // If this check is not here we'll produce endless recursion when something is done with the scope
    // during the callback.
    if (!this._notifyingListeners) {
      this._notifyingListeners = true;
      this._scopeListeners.forEach(callback => {
        callback(this);
      });
      this._notifyingListeners = false;
    }
  }

  /**
   * Applies fingerprint from the scope to the event if there's one,
   * uses message if there's one instead or get rid of empty fingerprint
   */
   _applyFingerprint(event) {
    // Make sure it's an array first and we actually have something in place
    event.fingerprint = event.fingerprint ? utils.arrayify(event.fingerprint) : [];

    // If we have something on the scope, then merge it with event
    if (this._fingerprint) {
      event.fingerprint = event.fingerprint.concat(this._fingerprint);
    }

    // If we have no data at all, remove empty array default
    if (event.fingerprint && !event.fingerprint.length) {
      delete event.fingerprint;
    }
  }
}

/**
 * Returns the global event processors.
 */
function getGlobalEventProcessors() {
  return utils.getGlobalSingleton('globalEventProcessors', () => []);
}

/**
 * Add a EventProcessor to be kept globally.
 * @param callback EventProcessor to add
 */
function addGlobalEventProcessor(callback) {
  getGlobalEventProcessors().push(callback);
}

exports.Scope = Scope;
exports.addGlobalEventProcessor = addGlobalEventProcessor;


},{"./session.js":31,"@sentry/utils":130}],30:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const hub = require('./hub.js');

/** A class object that can instantiate Client objects. */

/**
 * Internal function to create a new SDK client instance. The client is
 * installed and then bound to the current scope.
 *
 * @param clientClass The client class to instantiate.
 * @param options Options to pass to the client.
 */
function initAndBind(
  clientClass,
  options,
) {
  if (options.debug === true) {
    if ((typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__)) {
      utils.logger.enable();
    } else {
      // use `console.warn` rather than `logger.warn` since by non-debug bundles have all `logger.x` statements stripped
      // eslint-disable-next-line no-console
      console.warn('[Sentry] Cannot initialize SDK with `debug` option using a non-debug bundle.');
    }
  }
  const hub$1 = hub.getCurrentHub();
  const scope = hub$1.getScope();
  if (scope) {
    scope.update(options.initialScope);
  }

  const client = new clientClass(options);
  hub$1.bindClient(client);
}

exports.initAndBind = initAndBind;


},{"./hub.js":23,"@sentry/utils":130}],31:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

/**
 * Creates a new `Session` object by setting certain default parameters. If optional @param context
 * is passed, the passed properties are applied to the session object.
 *
 * @param context (optional) additional properties to be applied to the returned session object
 *
 * @returns a new `Session` object
 */
function makeSession(context) {
  // Both timestamp and started are in seconds since the UNIX epoch.
  const startingTime = utils.timestampInSeconds();

  const session = {
    sid: utils.uuid4(),
    init: true,
    timestamp: startingTime,
    started: startingTime,
    duration: 0,
    status: 'ok',
    errors: 0,
    ignoreDuration: false,
    toJSON: () => sessionToJSON(session),
  };

  if (context) {
    updateSession(session, context);
  }

  return session;
}

/**
 * Updates a session object with the properties passed in the context.
 *
 * Note that this function mutates the passed object and returns void.
 * (Had to do this instead of returning a new and updated session because closing and sending a session
 * makes an update to the session after it was passed to the sending logic.
 * @see BaseClient.captureSession )
 *
 * @param session the `Session` to update
 * @param context the `SessionContext` holding the properties that should be updated in @param session
 */
// eslint-disable-next-line complexity
function updateSession(session, context = {}) {
  if (context.user) {
    if (!session.ipAddress && context.user.ip_address) {
      session.ipAddress = context.user.ip_address;
    }

    if (!session.did && !context.did) {
      session.did = context.user.id || context.user.email || context.user.username;
    }
  }

  session.timestamp = context.timestamp || utils.timestampInSeconds();

  if (context.ignoreDuration) {
    session.ignoreDuration = context.ignoreDuration;
  }
  if (context.sid) {
    // Good enough uuid validation. — Kamil
    session.sid = context.sid.length === 32 ? context.sid : utils.uuid4();
  }
  if (context.init !== undefined) {
    session.init = context.init;
  }
  if (!session.did && context.did) {
    session.did = `${context.did}`;
  }
  if (typeof context.started === 'number') {
    session.started = context.started;
  }
  if (session.ignoreDuration) {
    session.duration = undefined;
  } else if (typeof context.duration === 'number') {
    session.duration = context.duration;
  } else {
    const duration = session.timestamp - session.started;
    session.duration = duration >= 0 ? duration : 0;
  }
  if (context.release) {
    session.release = context.release;
  }
  if (context.environment) {
    session.environment = context.environment;
  }
  if (!session.ipAddress && context.ipAddress) {
    session.ipAddress = context.ipAddress;
  }
  if (!session.userAgent && context.userAgent) {
    session.userAgent = context.userAgent;
  }
  if (typeof context.errors === 'number') {
    session.errors = context.errors;
  }
  if (context.status) {
    session.status = context.status;
  }
}

/**
 * Closes a session by setting its status and updating the session object with it.
 * Internally calls `updateSession` to update the passed session object.
 *
 * Note that this function mutates the passed session (@see updateSession for explanation).
 *
 * @param session the `Session` object to be closed
 * @param status the `SessionStatus` with which the session was closed. If you don't pass a status,
 *               this function will keep the previously set status, unless it was `'ok'` in which case
 *               it is changed to `'exited'`.
 */
function closeSession(session, status) {
  let context = {};
  if (status) {
    context = { status };
  } else if (session.status === 'ok') {
    context = { status: 'exited' };
  }

  updateSession(session, context);
}

/**
 * Serializes a passed session object to a JSON object with a slightly different structure.
 * This is necessary because the Sentry backend requires a slightly different schema of a session
 * than the one the JS SDKs use internally.
 *
 * @param session the session to be converted
 *
 * @returns a JSON object of the passed session
 */
function sessionToJSON(session) {
  return utils.dropUndefinedKeys({
    sid: `${session.sid}`,
    init: session.init,
    // Make sure that sec is converted to ms for date constructor
    started: new Date(session.started * 1000).toISOString(),
    timestamp: new Date(session.timestamp * 1000).toISOString(),
    status: session.status,
    errors: session.errors,
    did: typeof session.did === 'number' || typeof session.did === 'string' ? `${session.did}` : undefined,
    duration: session.duration,
    attrs: {
      release: session.release,
      environment: session.environment,
      ip_address: session.ipAddress,
      user_agent: session.userAgent,
    },
  });
}

exports.closeSession = closeSession;
exports.makeSession = makeSession;
exports.updateSession = updateSession;


},{"@sentry/utils":130}],32:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const hub = require('./hub.js');

/**
 * @inheritdoc
 */
class SessionFlusher  {
    __init() {this.flushTimeout = 60;}
   __init2() {this._pendingAggregates = {};}

   __init3() {this._isEnabled = true;}

   constructor(client, attrs) {;SessionFlusher.prototype.__init.call(this);SessionFlusher.prototype.__init2.call(this);SessionFlusher.prototype.__init3.call(this);
    this._client = client;
    // Call to setInterval, so that flush is called every 60 seconds
    this._intervalId = setInterval(() => this.flush(), this.flushTimeout * 1000);
    this._sessionAttrs = attrs;
  }

  /** Checks if `pendingAggregates` has entries, and if it does flushes them by calling `sendSession` */
   flush() {
    const sessionAggregates = this.getSessionAggregates();
    if (sessionAggregates.aggregates.length === 0) {
      return;
    }
    this._pendingAggregates = {};
    this._client.sendSession(sessionAggregates);
  }

  /** Massages the entries in `pendingAggregates` and returns aggregated sessions */
   getSessionAggregates() {
    const aggregates = Object.keys(this._pendingAggregates).map((key) => {
      return this._pendingAggregates[parseInt(key)];
    });

    const sessionAggregates = {
      attrs: this._sessionAttrs,
      aggregates,
    };
    return utils.dropUndefinedKeys(sessionAggregates);
  }

  /** JSDoc */
   close() {
    clearInterval(this._intervalId);
    this._isEnabled = false;
    this.flush();
  }

  /**
   * Wrapper function for _incrementSessionStatusCount that checks if the instance of SessionFlusher is enabled then
   * fetches the session status of the request from `Scope.getRequestSession().status` on the scope and passes them to
   * `_incrementSessionStatusCount` along with the start date
   */
   incrementSessionStatusCount() {
    if (!this._isEnabled) {
      return;
    }
    const scope = hub.getCurrentHub().getScope();
    const requestSession = scope && scope.getRequestSession();

    if (requestSession && requestSession.status) {
      this._incrementSessionStatusCount(requestSession.status, new Date());
      // This is not entirely necessarily but is added as a safe guard to indicate the bounds of a request and so in
      // case captureRequestSession is called more than once to prevent double count
      if (scope) {
        scope.setRequestSession(undefined);
      }
      /* eslint-enable @typescript-eslint/no-unsafe-member-access */
    }
  }

  /**
   * Increments status bucket in pendingAggregates buffer (internal state) corresponding to status of
   * the session received
   */
   _incrementSessionStatusCount(status, date) {
    // Truncate minutes and seconds on Session Started attribute to have one minute bucket keys
    const sessionStartedTrunc = new Date(date).setSeconds(0, 0);
    this._pendingAggregates[sessionStartedTrunc] = this._pendingAggregates[sessionStartedTrunc] || {};

    // corresponds to aggregated sessions in one specific minute bucket
    // for example, {"started":"2021-03-16T08:00:00.000Z","exited":4, "errored": 1}
    const aggregationCounts = this._pendingAggregates[sessionStartedTrunc];
    if (!aggregationCounts.started) {
      aggregationCounts.started = new Date(sessionStartedTrunc).toISOString();
    }

    switch (status) {
      case 'errored':
        aggregationCounts.errored = (aggregationCounts.errored || 0) + 1;
        return aggregationCounts.errored;
      case 'ok':
        aggregationCounts.exited = (aggregationCounts.exited || 0) + 1;
        return aggregationCounts.exited;
      default:
        aggregationCounts.crashed = (aggregationCounts.crashed || 0) + 1;
        return aggregationCounts.crashed;
    }
  }
}

exports.SessionFlusher = SessionFlusher;


},{"./hub.js":23,"@sentry/utils":130}],33:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

const DEFAULT_TRANSPORT_BUFFER_SIZE = 30;

/**
 * Creates an instance of a Sentry `Transport`
 *
 * @param options
 * @param makeRequest
 */
function createTransport(
  options,
  makeRequest,
  buffer = utils.makePromiseBuffer(options.bufferSize || DEFAULT_TRANSPORT_BUFFER_SIZE),
) {
  let rateLimits = {};

  const flush = (timeout) => buffer.drain(timeout);

  function send(envelope) {
    const filteredEnvelopeItems = [];

    // Drop rate limited items from envelope
    utils.forEachEnvelopeItem(envelope, (item, type) => {
      const envelopeItemDataCategory = utils.envelopeItemTypeToDataCategory(type);
      if (utils.isRateLimited(rateLimits, envelopeItemDataCategory)) {
        const event = getEventForEnvelopeItem(item, type);
        options.recordDroppedEvent('ratelimit_backoff', envelopeItemDataCategory, event);
      } else {
        filteredEnvelopeItems.push(item);
      }
    });

    // Skip sending if envelope is empty after filtering out rate limited events
    if (filteredEnvelopeItems.length === 0) {
      return utils.resolvedSyncPromise();
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const filteredEnvelope = utils.createEnvelope(envelope[0], filteredEnvelopeItems );

    // Creates client report for each item in an envelope
    const recordEnvelopeLoss = (reason) => {
      utils.forEachEnvelopeItem(filteredEnvelope, (item, type) => {
        const event = getEventForEnvelopeItem(item, type);
        options.recordDroppedEvent(reason, utils.envelopeItemTypeToDataCategory(type), event);
      });
    };

    const requestTask = () =>
      makeRequest({ body: utils.serializeEnvelope(filteredEnvelope, options.textEncoder) }).then(
        response => {
          // We don't want to throw on NOK responses, but we want to at least log them
          if (response.statusCode !== undefined && (response.statusCode < 200 || response.statusCode >= 300)) {
            (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.warn(`Sentry responded with status code ${response.statusCode} to sent event.`);
          }

          rateLimits = utils.updateRateLimits(rateLimits, response);
        },
        error => {
          (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('Failed while sending event:', error);
          recordEnvelopeLoss('network_error');
        },
      );

    return buffer.add(requestTask).then(
      result => result,
      error => {
        if (error instanceof utils.SentryError) {
          (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('Skipped sending event because buffer is full.');
          recordEnvelopeLoss('queue_overflow');
          return utils.resolvedSyncPromise();
        } else {
          throw error;
        }
      },
    );
  }

  return {
    send,
    flush,
  };
}

function getEventForEnvelopeItem(item, type) {
  if (type !== 'event' && type !== 'transaction') {
    return undefined;
  }

  return Array.isArray(item) ? (item )[1] : undefined;
}

exports.DEFAULT_TRANSPORT_BUFFER_SIZE = DEFAULT_TRANSPORT_BUFFER_SIZE;
exports.createTransport = createTransport;


},{"@sentry/utils":130}],34:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const SDK_VERSION = '7.28.0';

exports.SDK_VERSION = SDK_VERSION;


},{}],35:[function(require,module,exports){
(function (global){(function (){
Object.defineProperty(exports, '__esModule', { value: true });

var commonjsGlobal = typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : typeof global !== 'undefined' ? global : typeof self !== 'undefined' ? self : {};

function getDefaultExportFromCjs (x) {
	return x && x.__esModule && Object.prototype.hasOwnProperty.call(x, 'default') ? x['default'] : x;
}

function getDefaultExportFromNamespaceIfPresent (n) {
	return n && Object.prototype.hasOwnProperty.call(n, 'default') ? n['default'] : n;
}

function getDefaultExportFromNamespaceIfNotNamed (n) {
	return n && Object.prototype.hasOwnProperty.call(n, 'default') && Object.keys(n).length === 1 ? n['default'] : n;
}

function getAugmentedNamespace(n) {
	if (n.__esModule) return n;
	var a = Object.defineProperty({}, '__esModule', {value: true});
	Object.keys(n).forEach(function (k) {
		var d = Object.getOwnPropertyDescriptor(n, k);
		Object.defineProperty(a, k, d.get ? d : {
			enumerable: true,
			get: function () {
				return n[k];
			}
		});
	});
	return a;
}

function commonjsRequire (path) {
	throw new Error('Could not dynamically require "' + path + '". Please configure the dynamicRequireTargets or/and ignoreDynamicRequires option of @rollup/plugin-commonjs appropriately for this require call to work.');
}

exports.commonjsGlobal = commonjsGlobal;
exports.commonjsRequire = commonjsRequire;
exports.getAugmentedNamespace = getAugmentedNamespace;
exports.getDefaultExportFromCjs = getDefaultExportFromCjs;
exports.getDefaultExportFromNamespaceIfNotNamed = getDefaultExportFromNamespaceIfNotNamed;
exports.getDefaultExportFromNamespaceIfPresent = getDefaultExportFromNamespaceIfPresent;


}).call(this)}).call(this,typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : {})
},{}],36:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

// exporting a separate copy of `WINDOW` rather than exporting the one from `@sentry/browser`
// prevents the browser package from being bundled in the CDN bundle, and avoids a
// circular dependency between the browser and replay packages should `@sentry/browser` import
// from `@sentry/replay` in the future
const WINDOW = utils.GLOBAL_OBJ ;

const REPLAY_SESSION_KEY = 'sentryReplaySession';
const REPLAY_EVENT_NAME = 'replay_event';
const RECORDING_EVENT_NAME = 'replay_recording';
const UNABLE_TO_SEND_REPLAY = 'Unable to send Replay';

// The idle limit for a session
const SESSION_IDLE_DURATION = 300000; // 5 minutes in ms

// Grace period to keep a session when a user changes tabs or hides window
const VISIBILITY_CHANGE_TIMEOUT = SESSION_IDLE_DURATION;

// The maximum length of a session
const MAX_SESSION_LIFE = 3600000; // 60 minutes

/**
 * Defaults for sampling rates
 */
const DEFAULT_SESSION_SAMPLE_RATE = 0.1;
const DEFAULT_ERROR_SAMPLE_RATE = 1.0;

/** The select to use for the `maskAllText` option  */
const MASK_ALL_TEXT_SELECTOR = 'body *:not(style,script)';

exports.DEFAULT_ERROR_SAMPLE_RATE = DEFAULT_ERROR_SAMPLE_RATE;
exports.DEFAULT_SESSION_SAMPLE_RATE = DEFAULT_SESSION_SAMPLE_RATE;
exports.MASK_ALL_TEXT_SELECTOR = MASK_ALL_TEXT_SELECTOR;
exports.MAX_SESSION_LIFE = MAX_SESSION_LIFE;
exports.RECORDING_EVENT_NAME = RECORDING_EVENT_NAME;
exports.REPLAY_EVENT_NAME = REPLAY_EVENT_NAME;
exports.REPLAY_SESSION_KEY = REPLAY_SESSION_KEY;
exports.SESSION_IDLE_DURATION = SESSION_IDLE_DURATION;
exports.UNABLE_TO_SEND_REPLAY = UNABLE_TO_SEND_REPLAY;
exports.VISIBILITY_CHANGE_TIMEOUT = VISIBILITY_CHANGE_TIMEOUT;
exports.WINDOW = WINDOW;


},{"@sentry/utils":130}],37:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const handleDom = require('./handleDom.js');
const handleScope = require('./handleScope.js');

function breadcrumbHandler(type, handlerData) {
  if (type === 'scope') {
    return handleScope.handleScope(handlerData );
  }

  return handleDom.handleDom(handlerData );
}

exports.breadcrumbHandler = breadcrumbHandler;


},{"./handleDom.js":38,"./handleScope.js":42}],38:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
require('../node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js');
const createBreadcrumb = require('../util/createBreadcrumb.js');
const index = require('../node_modules/rrweb/es/rrweb/packages/rrweb/src/record/index.js');

function handleDom(handlerData) {
  // Taken from https://github.com/getsentry/sentry-javascript/blob/master/packages/browser/src/integrations/breadcrumbs.ts#L112
  let target;
  let targetNode;

  // Accessing event.target can throw (see getsentry/raven-js#838, #768)
  try {
    targetNode = getTargetNode(handlerData);
    target = utils.htmlTreeAsString(targetNode);
  } catch (e) {
    target = '<unknown>';
  }

  if (target.length === 0) {
    return null;
  }

  return createBreadcrumb.createBreadcrumb({
    category: `ui.${handlerData.name}`,
    message: target,
    data: {
      // Not sure why this errors, Node should be correct (Argument of type 'Node' is not assignable to parameter of type 'INode')
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ...(targetNode ? { nodeId: index.default.mirror.getId(targetNode ) } : {}),
    },
  });
}

function getTargetNode(handlerData) {
  if (isEventWithTarget(handlerData.event)) {
    return handlerData.event.target;
  }

  return handlerData.event;
}

function isEventWithTarget(event) {
  return !!(event ).target;
}

exports.handleDom = handleDom;


},{"../node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js":56,"../node_modules/rrweb/es/rrweb/packages/rrweb/src/record/index.js":66,"../util/createBreadcrumb.js":95,"@sentry/utils":130}],39:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const createPerformanceSpans = require('../util/createPerformanceSpans.js');
const shouldFilterRequest = require('../util/shouldFilterRequest.js');

/** only exported for tests */
function handleFetch(handlerData) {
  if (!handlerData.endTimestamp) {
    return null;
  }

  const { startTimestamp, endTimestamp, fetchData, response } = handlerData;

  return {
    type: 'resource.fetch',
    start: startTimestamp / 1000,
    end: endTimestamp / 1000,
    name: fetchData.url,
    data: {
      method: fetchData.method,
      statusCode: response.status,
    },
  };
}

/**
 * Returns a listener to be added to `addInstrumentationHandler('fetch', listener)`.
 */
function handleFetchSpanListener(replay) {
  return (handlerData) => {
    if (!replay.isEnabled()) {
      return;
    }

    const result = handleFetch(handlerData);

    if (result === null) {
      return;
    }

    if (shouldFilterRequest.shouldFilterRequest(replay, result.name)) {
      return;
    }

    replay.addUpdate(() => {
      createPerformanceSpans.createPerformanceSpans(replay, [result]);
      // Returning true will cause `addUpdate` to not flush
      // We do not want network requests to cause a flush. This will prevent
      // recurring/polling requests from keeping the replay session alive.
      return true;
    });
  };
}

exports.handleFetch = handleFetch;
exports.handleFetchSpanListener = handleFetchSpanListener;


},{"../util/createPerformanceSpans.js":97,"../util/shouldFilterRequest.js":107}],40:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const constants = require('../constants.js');
const isRrwebError = require('../util/isRrwebError.js');

/**
 * Returns a listener to be added to `addGlobalEventProcessor(listener)`.
 */
function handleGlobalEventListener(replay) {
  return (event) => {
    // Do not apply replayId to the root event
    if (
      // @ts-ignore new event type
      event.type === constants.REPLAY_EVENT_NAME
    ) {
      // Replays have separate set of breadcrumbs, do not include breadcrumbs
      // from core SDK
      delete event.breadcrumbs;
      return event;
    }

    // Unless `captureExceptions` is enabled, we want to ignore errors coming from rrweb
    // As there can be a bunch of stuff going wrong in internals there, that we don't want to bubble up to users
    if (isRrwebError.isRrwebError(event) && !_optionalChain([replay, 'access', _ => _.getOptions, 'call', _2 => _2(), 'access', _3 => _3._experiments, 'optionalAccess', _4 => _4.captureExceptions])) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Ignoring error from rrweb internals', event);
      return null;
    }

    // Only tag transactions with replayId if not waiting for an error
    // @ts-ignore private
    if (event.type !== 'transaction' || replay.recordingMode === 'session') {
      event.tags = { ...event.tags, replayId: _optionalChain([replay, 'access', _5 => _5.session, 'optionalAccess', _6 => _6.id]) };
    }

    // Collect traceIds in _context regardless of `recordingMode` - if it's true,
    // _context gets cleared on every checkout
    if (event.type === 'transaction' && event.contexts && event.contexts.trace && event.contexts.trace.trace_id) {
      replay.getContext().traceIds.add(event.contexts.trace.trace_id );
      return event;
    }

    // no event type means error
    if (!event.type) {
      replay.getContext().errorIds.add(event.event_id );
    }

    const exc = _optionalChain([event, 'access', _7 => _7.exception, 'optionalAccess', _8 => _8.values, 'optionalAccess', _9 => _9[0]]);
    if ((typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && _optionalChain([replay, 'access', _10 => _10.getOptions, 'call', _11 => _11(), 'access', _12 => _12._experiments, 'optionalAccess', _13 => _13.traceInternals])) {
      addInternalBreadcrumb({
        message: `Tagging event (${event.event_id}) - ${event.message} - ${_optionalChain([exc, 'optionalAccess', _14 => _14.type]) || 'Unknown'}: ${
          _optionalChain([exc, 'optionalAccess', _15 => _15.value]) || 'n/a'
        }`,
      });
    }

    // Need to be very careful that this does not cause an infinite loop
    if (
      replay.recordingMode === 'error' &&
      event.exception &&
      event.message !== constants.UNABLE_TO_SEND_REPLAY // ignore this error because otherwise we could loop indefinitely with trying to capture replay and failing
    ) {
      setTimeout(async () => {
        // Allow flush to complete before resuming as a session recording, otherwise
        // the checkout from `startRecording` may be included in the payload.
        // Prefer to keep the error replay as a separate (and smaller) segment
        // than the session replay.
        await replay.flushImmediate();

        if (replay.stopRecording()) {
          // Reset all "capture on error" configuration before
          // starting a new recording
          replay.recordingMode = 'session';
          replay.startRecording();
        }
      });
    }

    return event;
  };
}

function addInternalBreadcrumb(arg) {
  const { category, level, message, ...rest } = arg;

  core.addBreadcrumb({
    category: category || 'console',
    level: level || 'debug',
    message: `[debug]: ${message}`,
    ...rest,
  });
}

exports.handleGlobalEventListener = handleGlobalEventListener;


},{"../constants.js":36,"../util/isRrwebError.js":103,"@sentry/core":24,"@sentry/utils":130,"@sentry/utils/cjs/buildPolyfills":124}],41:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const createPerformanceSpans = require('../util/createPerformanceSpans.js');

function handleHistory(handlerData) {
  const { from, to } = handlerData;

  const now = new Date().getTime() / 1000;

  return {
    type: 'navigation.push',
    start: now,
    end: now,
    name: to,
    data: {
      previous: from,
    },
  };
}

/**
 * Returns a listener to be added to `addInstrumentationHandler('history', listener)`.
 */
function handleHistorySpanListener(replay) {
  return (handlerData) => {
    if (!replay.isEnabled()) {
      return;
    }

    const result = handleHistory(handlerData);

    if (result === null) {
      return;
    }

    // Need to collect visited URLs
    replay.getContext().urls.push(result.name);
    replay.triggerUserActivity();

    replay.addUpdate(() => {
      createPerformanceSpans.createPerformanceSpans(replay, [result]);
      // Returning false to flush
      return false;
    });
  };
}

exports.handleHistorySpanListener = handleHistorySpanListener;


},{"../util/createPerformanceSpans.js":97}],42:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const createBreadcrumb = require('../util/createBreadcrumb.js');

let _LAST_BREADCRUMB = null;

function handleScope(scope) {
  const newBreadcrumb = scope.getLastBreadcrumb();

  // Listener can be called when breadcrumbs have not changed, so we store the
  // reference to the last crumb and only return a crumb if it has changed
  if (_LAST_BREADCRUMB === newBreadcrumb || !newBreadcrumb) {
    return null;
  }

  _LAST_BREADCRUMB = newBreadcrumb;

  if (
    newBreadcrumb.category &&
    (['fetch', 'xhr', 'sentry.event', 'sentry.transaction'].includes(newBreadcrumb.category) ||
      newBreadcrumb.category.startsWith('ui.'))
  ) {
    return null;
  }

  return createBreadcrumb.createBreadcrumb(newBreadcrumb);
}

exports.handleScope = handleScope;


},{"../util/createBreadcrumb.js":95}],43:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const createPerformanceSpans = require('../util/createPerformanceSpans.js');
const shouldFilterRequest = require('../util/shouldFilterRequest.js');

// From sentry-javascript
// e.g. https://github.com/getsentry/sentry-javascript/blob/c7fc025bf9fa8c073fdb56351808ce53909fbe45/packages/utils/src/instrument.ts#L180

function handleXhr(handlerData) {
  if (handlerData.xhr.__sentry_own_request__) {
    // Taken from sentry-javascript
    // Only capture non-sentry requests
    return null;
  }

  if (handlerData.startTimestamp) {
    // TODO: See if this is still needed
    handlerData.xhr.__sentry_xhr__ = handlerData.xhr.__sentry_xhr__ || {};
    handlerData.xhr.__sentry_xhr__.startTimestamp = handlerData.startTimestamp;
  }

  if (!handlerData.endTimestamp) {
    return null;
  }

  const { method, url, status_code: statusCode } = handlerData.xhr.__sentry_xhr__ || {};

  if (url === undefined) {
    return null;
  }

  return {
    type: 'resource.xhr',
    name: url,
    start: (_optionalChain([handlerData, 'access', _ => _.xhr, 'access', _2 => _2.__sentry_xhr__, 'optionalAccess', _3 => _3.startTimestamp]) || 0) / 1000 || handlerData.endTimestamp / 1000.0,
    end: handlerData.endTimestamp / 1000.0,
    data: {
      method,
      statusCode,
    },
  };
}

/**
 * Returns a listener to be added to `addInstrumentationHandler('xhr', listener)`.
 */
function handleXhrSpanListener(replay) {
  return (handlerData) => {
    if (!replay.isEnabled()) {
      return;
    }

    const result = handleXhr(handlerData);

    if (result === null) {
      return;
    }

    if (shouldFilterRequest.shouldFilterRequest(replay, result.name)) {
      return;
    }

    replay.addUpdate(() => {
      createPerformanceSpans.createPerformanceSpans(replay, [result]);
      // Returning true will cause `addUpdate` to not flush
      // We do not want network requests to cause a flush. This will prevent
      // recurring/polling requests from keeping the replay session alive.
      return true;
    });
  };
}

exports.handleXhrSpanListener = handleXhrSpanListener;


},{"../util/createPerformanceSpans.js":97,"../util/shouldFilterRequest.js":107,"@sentry/utils/cjs/buildPolyfills":124}],44:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const dedupePerformanceEntries = require('../util/dedupePerformanceEntries.js');

/**
 * Sets up a PerformanceObserver to listen to all performance entry types.
 */
function setupPerformanceObserver(replay) {
  const performanceObserverHandler = (list) => {
    // For whatever reason the observer was returning duplicate navigation
    // entries (the other entry types were not duplicated).
    const newPerformanceEntries = dedupePerformanceEntries.dedupePerformanceEntries(
      replay.performanceEvents,
      list.getEntries() ,
    );
    replay.performanceEvents = newPerformanceEntries;
  };

  const performanceObserver = new PerformanceObserver(performanceObserverHandler);

  [
    'element',
    'event',
    'first-input',
    'largest-contentful-paint',
    'layout-shift',
    'longtask',
    'navigation',
    'paint',
    'resource',
  ].forEach(type => {
    try {
      performanceObserver.observe({
        type,
        buffered: true,
      });
    } catch (e) {
      // This can throw if an entry type is not supported in the browser.
      // Ignore these errors.
    }
  });

  return performanceObserver;
}

exports.setupPerformanceObserver = setupPerformanceObserver;


},{"../util/dedupePerformanceEntries.js":99}],45:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
require('./node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js');
const constants = require('./constants.js');
const index = require('./node_modules/rrweb/es/rrweb/packages/rrweb/src/record/index.js');

// Map entryType -> function to normalize data for event
// @ts-ignore TODO: entry type does not fit the create* functions entry type
const ENTRY_TYPES = {
  // @ts-ignore TODO: entry type does not fit the create* functions entry type
  resource: createResourceEntry,
  paint: createPaintEntry,
  // @ts-ignore TODO: entry type does not fit the create* functions entry type
  navigation: createNavigationEntry,
  // @ts-ignore TODO: entry type does not fit the create* functions entry type
  ['largest-contentful-paint']: createLargestContentfulPaint,
};

function createPerformanceEntries(entries) {
  return entries.map(createPerformanceEntry).filter(Boolean) ;
}

function createPerformanceEntry(entry) {
  if (ENTRY_TYPES[entry.entryType] === undefined) {
    return null;
  }

  return ENTRY_TYPES[entry.entryType](entry);
}

function getAbsoluteTime(time) {
  // browserPerformanceTimeOrigin can be undefined if `performance` or
  // `performance.now` doesn't exist, but this is already checked by this integration
  return ((utils.browserPerformanceTimeOrigin || constants.WINDOW.performance.timeOrigin) + time) / 1000;
}

// TODO: type definition!
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
function createPaintEntry(entry) {
  const { duration, entryType, name, startTime } = entry;

  const start = getAbsoluteTime(startTime);
  return {
    type: entryType,
    name,
    start,
    end: start + duration,
  };
}

// TODO: type definition!
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
function createNavigationEntry(entry) {
  // TODO: There looks to be some more interesting bits in here (domComplete, domContentLoaded)
  const { entryType, name, duration, domComplete, startTime, transferSize, type } = entry;

  // Ignore entries with no duration, they do not seem to be useful and cause dupes
  if (duration === 0) {
    return null;
  }

  return {
    type: `${entryType}.${type}`,
    start: getAbsoluteTime(startTime),
    end: getAbsoluteTime(domComplete),
    name,
    data: {
      size: transferSize,
      duration,
    },
  };
}

// TODO: type definition!
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
function createResourceEntry(entry) {
  const { entryType, initiatorType, name, responseEnd, startTime, encodedBodySize, transferSize } = entry;

  // Core SDK handles these
  if (['fetch', 'xmlhttprequest'].includes(initiatorType)) {
    return null;
  }

  return {
    type: `${entryType}.${initiatorType}`,
    start: getAbsoluteTime(startTime),
    end: getAbsoluteTime(responseEnd),
    name,
    data: {
      size: transferSize,
      encodedBodySize,
    },
  };
}

// TODO: type definition!
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
function createLargestContentfulPaint(entry) {
  const { duration, entryType, startTime, size } = entry;

  const start = getAbsoluteTime(startTime);

  return {
    type: entryType,
    name: entryType,
    start,
    end: start + duration,
    data: {
      duration,
      size,
      // Not sure why this errors, Node should be correct (Argument of type 'Node' is not assignable to parameter of type 'INode')
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      nodeId: index.default.mirror.getId(entry.element ),
    },
  };
}

function createMemoryEntry(memoryEntry) {
  const { jsHeapSizeLimit, totalJSHeapSize, usedJSHeapSize } = memoryEntry;
  // we don't want to use `getAbsoluteTime` because it adds the event time to the
  // time origin, so we get the current timestamp instead
  const time = new Date().getTime() / 1000;
  return {
    type: 'memory',
    name: 'memory',
    start: time,
    end: time,
    data: {
      memory: {
        jsHeapSizeLimit,
        totalJSHeapSize,
        usedJSHeapSize,
      },
    },
  };
}

exports.createMemoryEntry = createMemoryEntry;
exports.createPerformanceEntries = createPerformanceEntries;


},{"./constants.js":36,"./node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js":56,"./node_modules/rrweb/es/rrweb/packages/rrweb/src/record/index.js":66,"@sentry/utils":130}],46:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const worker = require('./worker/worker.js');

/* eslint-disable @typescript-eslint/no-unsafe-member-access */

function createEventBuffer({ useCompression }) {
  // eslint-disable-next-line no-restricted-globals
  if (useCompression && window.Worker) {
    const workerBlob = new Blob([worker.default]);
    const workerUrl = URL.createObjectURL(workerBlob);

    try {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Using compression worker');
      const worker = new Worker(workerUrl);
      if (worker) {
        return new EventBufferCompressionWorker(worker);
      } else {
        core.captureException(new Error('Unable to create compression worker'));
      }
    } catch (e) {
      // catch and ignore, fallback to simple event buffer
    }
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Falling back to simple event buffer');
  }

  (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Using simple buffer');
  return new EventBufferArray();
}

class EventBufferArray  {

   constructor() {
    this._events = [];
  }

   destroy() {
    this._events = [];
  }

   get length() {
    return this._events.length;
  }

   addEvent(event, isCheckout) {
    if (isCheckout) {
      this._events = [event];
      return;
    }

    this._events.push(event);
  }

   finish() {
    return new Promise(resolve => {
      // Make a copy of the events array reference and immediately clear the
      // events member so that we do not lose new events while uploading
      // attachment.
      const eventsRet = this._events;
      this._events = [];
      resolve(JSON.stringify(eventsRet));
    });
  }
}

// exporting for testing
class EventBufferCompressionWorker  {

   __init() {this._eventBufferItemLength = 0;}
   __init2() {this._id = 0;}

   constructor(worker) {;EventBufferCompressionWorker.prototype.__init.call(this);EventBufferCompressionWorker.prototype.__init2.call(this);
    this._worker = worker;
  }

   destroy() {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Destroying compression worker');
    _optionalChain([this, 'access', _ => _._worker, 'optionalAccess', _2 => _2.terminate, 'call', _3 => _3()]);
    this._worker = null;
  }

  /**
   * Note that this may not reflect what is actually in the event buffer. This
   * is only a local count of the buffer size since `addEvent` is async.
   */
   get length() {
    return this._eventBufferItemLength;
  }

   async addEvent(event, isCheckout) {
    if (isCheckout) {
      // This event is a checkout, make sure worker buffer is cleared before
      // proceeding.
      await this._postMessage({
        id: this._getAndIncrementId(),
        method: 'init',
        args: [],
      });
    }

    return this._sendEventToWorker(event);
  }

   finish() {
    return this._finishRequest(this._getAndIncrementId());
  }

  /**
   * Post message to worker and wait for response before resolving promise.
   */
   _postMessage({ id, method, args }) {
    return new Promise((resolve, reject) => {
      // eslint-disable-next-line @typescript-eslint/explicit-function-return-type
      const listener = ({ data }) => {
        if (data.method !== method) {
          return;
        }

        // There can be multiple listeners for a single method, the id ensures
        // that the response matches the caller.
        if (data.id !== id) {
          return;
        }

        // At this point, we'll always want to remove listener regardless of result status
        _optionalChain([this, 'access', _4 => _4._worker, 'optionalAccess', _5 => _5.removeEventListener, 'call', _6 => _6('message', listener)]);

        if (!data.success) {
          // TODO: Do some error handling, not sure what
          (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('[Replay]', data.response);

          reject(new Error('Error in compression worker'));
          return;
        }

        resolve(data.response);
      };

      let stringifiedArgs;
      try {
        stringifiedArgs = JSON.stringify(args);
      } catch (err) {
        (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('[Replay] Error when trying to stringify args', err);
        stringifiedArgs = '[]';
      }

      // Note: we can't use `once` option because it's possible it needs to
      // listen to multiple messages
      _optionalChain([this, 'access', _7 => _7._worker, 'optionalAccess', _8 => _8.addEventListener, 'call', _9 => _9('message', listener)]);
      _optionalChain([this, 'access', _10 => _10._worker, 'optionalAccess', _11 => _11.postMessage, 'call', _12 => _12({ id, method, args: stringifiedArgs })]);
    });
  }

   _sendEventToWorker(event) {
    const promise = this._postMessage({
      id: this._getAndIncrementId(),
      method: 'addEvent',
      args: [event],
    });

    // XXX: See note in `get length()`
    this._eventBufferItemLength++;

    return promise;
  }

   async _finishRequest(id) {
    const promise = this._postMessage({ id, method: 'finish', args: [] });

    // XXX: See note in `get length()`
    this._eventBufferItemLength = 0;

    return promise ;
  }

   _getAndIncrementId() {
    return this._id++;
  }
}

exports.EventBufferCompressionWorker = EventBufferCompressionWorker;
exports.createEventBuffer = createEventBuffer;


},{"./worker/worker.js":108,"@sentry/core":24,"@sentry/utils":130,"@sentry/utils/cjs/buildPolyfills":124}],47:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const integration = require('./integration.js');



exports.Replay = integration.Replay;


},{"./integration.js":48}],48:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const constants = require('./constants.js');
const replay = require('./replay.js');
const isBrowser = require('./util/isBrowser.js');

const MEDIA_SELECTORS = 'img,image,svg,path,rect,area,video,object,picture,embed,map,audio';

let _initialized = false;

class Replay  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Replay';}

  /**
   * @inheritDoc
   */
   __init() {this.name = Replay.id;}

  /**
   * Options to pass to `rrweb.record()`
   */

   get _isInitialized() {
    return _initialized;
  }

   set _isInitialized(value) {
    _initialized = value;
  }

  constructor({
    flushMinDelay = 5000,
    flushMaxDelay = 15000,
    initialFlushDelay = 5000,
    stickySession = true,
    useCompression = true,
    sessionSampleRate,
    errorSampleRate,
    maskAllText = true,
    maskAllInputs = true,
    blockAllMedia = true,
    _experiments = {},
    blockClass = 'sentry-block',
    ignoreClass = 'sentry-ignore',
    maskTextClass = 'sentry-mask',
    blockSelector = '[data-sentry-block]',
    ...recordingOptions
  } = {}) {;Replay.prototype.__init.call(this);
    this.recordingOptions = {
      maskAllInputs,
      blockClass,
      ignoreClass,
      maskTextClass,
      blockSelector,
      ...recordingOptions,
    };

    this.options = {
      flushMinDelay,
      flushMaxDelay,
      stickySession,
      initialFlushDelay,
      sessionSampleRate: constants.DEFAULT_SESSION_SAMPLE_RATE,
      errorSampleRate: constants.DEFAULT_ERROR_SAMPLE_RATE,
      useCompression,
      maskAllText,
      blockAllMedia,
      _experiments,
    };

    if (typeof sessionSampleRate === 'number') {
      // eslint-disable-next-line
      console.warn(
        `[Replay] You are passing \`sessionSampleRate\` to the Replay integration.
This option is deprecated and will be removed soon.
Instead, configure \`replaysSessionSampleRate\` directly in the SDK init options, e.g.:
Sentry.init({ replaysSessionSampleRate: ${sessionSampleRate} })`,
      );

      this.options.sessionSampleRate = sessionSampleRate;
    }

    if (typeof errorSampleRate === 'number') {
      // eslint-disable-next-line
      console.warn(
        `[Replay] You are passing \`errorSampleRate\` to the Replay integration.
This option is deprecated and will be removed soon.
Instead, configure \`replaysOnErrorSampleRate\` directly in the SDK init options, e.g.:
Sentry.init({ replaysOnErrorSampleRate: ${errorSampleRate} })`,
      );

      this.options.errorSampleRate = errorSampleRate;
    }

    if (this.options.maskAllText) {
      // `maskAllText` is a more user friendly option to configure
      // `maskTextSelector`. This means that all nodes will have their text
      // content masked.
      this.recordingOptions.maskTextSelector = constants.MASK_ALL_TEXT_SELECTOR;
    }

    if (this.options.blockAllMedia) {
      // `blockAllMedia` is a more user friendly option to configure blocking
      // embedded media elements
      this.recordingOptions.blockSelector = !this.recordingOptions.blockSelector
        ? MEDIA_SELECTORS
        : `${this.recordingOptions.blockSelector},${MEDIA_SELECTORS}`;
    }

    if (isBrowser.isBrowser() && this._isInitialized) {
      throw new Error('Multiple Sentry Session Replay instances are not supported');
    }

    this._isInitialized = true;
  }

  /**
   * We previously used to create a transaction in `setupOnce` and it would
   * potentially create a transaction before some native SDK integrations have run
   * and applied their own global event processor. An example is:
   * https://github.com/getsentry/sentry-javascript/blob/b47ceafbdac7f8b99093ce6023726ad4687edc48/packages/browser/src/integrations/useragent.ts
   *
   * So we call `replay.setup` in next event loop as a workaround to wait for other
   * global event processors to finish. This is no longer needed, but keeping it
   * here to avoid any future issues.
   */
  setupOnce() {
    if (!isBrowser.isBrowser()) {
      return;
    }

    this._setup();

    // XXX: See method comments above
    setTimeout(() => this.start());
  }

  /**
   * Initializes the plugin.
   *
   * Creates or loads a session, attaches listeners to varying events (DOM,
   * PerformanceObserver, Recording, Sentry SDK, etc)
   */
  start() {
    if (!this._replay) {
      return;
    }

    this._replay.start();
  }

  /**
   * Currently, this needs to be manually called (e.g. for tests). Sentry SDK
   * does not support a teardown
   */
  stop() {
    if (!this._replay) {
      return;
    }

    this._replay.stop();
  }

   _setup() {
    // Client is not available in constructor, so we need to wait until setupOnce
    this._loadReplayOptionsFromClient();

    this._replay = new replay.ReplayContainer({
      options: this.options,
      recordingOptions: this.recordingOptions,
    });
  }

  /** Parse Replay-related options from SDK options */
   _loadReplayOptionsFromClient() {
    const client = core.getCurrentHub().getClient();
    const opt = client && (client.getOptions() );

    if (opt && typeof opt.replaysSessionSampleRate === 'number') {
      this.options.sessionSampleRate = opt.replaysSessionSampleRate;
    }

    if (opt && typeof opt.replaysOnErrorSampleRate === 'number') {
      this.options.errorSampleRate = opt.replaysOnErrorSampleRate;
    }
  }
} Replay.__initStatic();

exports.Replay = Replay;


},{"./constants.js":36,"./replay.js":86,"./util/isBrowser.js":101,"@sentry/core":24}],49:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _commonjsHelpers = require('../../_virtual/_commonjsHelpers.js');

/**
 * lodash (Custom Build) <https://lodash.com/>
 * Build: `lodash modularize exports="npm" -o ./`
 * Copyright jQuery Foundation and other contributors <https://jquery.org/>
 * Released under MIT license <https://lodash.com/license>
 * Based on Underscore.js 1.8.3 <http://underscorejs.org/LICENSE>
 * Copyright Jeremy Ashkenas, DocumentCloud and Investigative Reporters & Editors
 */

/** Used as the `TypeError` message for "Functions" methods. */
var FUNC_ERROR_TEXT = 'Expected a function';

/** Used as references for various `Number` constants. */
var NAN = 0 / 0;

/** `Object#toString` result references. */
var symbolTag = '[object Symbol]';

/** Used to match leading and trailing whitespace. */
var reTrim = /^\s+|\s+$/g;

/** Used to detect bad signed hexadecimal string values. */
var reIsBadHex = /^[-+]0x[0-9a-f]+$/i;

/** Used to detect binary string values. */
var reIsBinary = /^0b[01]+$/i;

/** Used to detect octal string values. */
var reIsOctal = /^0o[0-7]+$/i;

/** Built-in method references without a dependency on `root`. */
var freeParseInt = parseInt;

/** Detect free variable `global` from Node.js. */
var freeGlobal = typeof _commonjsHelpers.commonjsGlobal == 'object' && _commonjsHelpers.commonjsGlobal && _commonjsHelpers.commonjsGlobal.Object === Object && _commonjsHelpers.commonjsGlobal;

/** Detect free variable `self`. */
var freeSelf = typeof self == 'object' && self && self.Object === Object && self;

/** Used as a reference to the global object. */
var root = freeGlobal || freeSelf;

/** Used for built-in method references. */
var objectProto = Object.prototype;

/**
 * Used to resolve the
 * [`toStringTag`](http://ecma-international.org/ecma-262/7.0/#sec-object.prototype.tostring)
 * of values.
 */
var objectToString = objectProto.toString;

/* Built-in method references for those with the same name as other `lodash` methods. */
var nativeMax = Math.max,
    nativeMin = Math.min;

/**
 * Gets the timestamp of the number of milliseconds that have elapsed since
 * the Unix epoch (1 January 1970 00:00:00 UTC).
 *
 * @static
 * @memberOf _
 * @since 2.4.0
 * @category Date
 * @returns {number} Returns the timestamp.
 * @example
 *
 * _.defer(function(stamp) {
 *   console.log(_.now() - stamp);
 * }, _.now());
 * // => Logs the number of milliseconds it took for the deferred invocation.
 */
var now = function() {
  return root.Date.now();
};

/**
 * Creates a debounced function that delays invoking `func` until after `wait`
 * milliseconds have elapsed since the last time the debounced function was
 * invoked. The debounced function comes with a `cancel` method to cancel
 * delayed `func` invocations and a `flush` method to immediately invoke them.
 * Provide `options` to indicate whether `func` should be invoked on the
 * leading and/or trailing edge of the `wait` timeout. The `func` is invoked
 * with the last arguments provided to the debounced function. Subsequent
 * calls to the debounced function return the result of the last `func`
 * invocation.
 *
 * **Note:** If `leading` and `trailing` options are `true`, `func` is
 * invoked on the trailing edge of the timeout only if the debounced function
 * is invoked more than once during the `wait` timeout.
 *
 * If `wait` is `0` and `leading` is `false`, `func` invocation is deferred
 * until to the next tick, similar to `setTimeout` with a timeout of `0`.
 *
 * See [David Corbacho's article](https://css-tricks.com/debouncing-throttling-explained-examples/)
 * for details over the differences between `_.debounce` and `_.throttle`.
 *
 * @static
 * @memberOf _
 * @since 0.1.0
 * @category Function
 * @param {Function} func The function to debounce.
 * @param {number} [wait=0] The number of milliseconds to delay.
 * @param {Object} [options={}] The options object.
 * @param {boolean} [options.leading=false]
 *  Specify invoking on the leading edge of the timeout.
 * @param {number} [options.maxWait]
 *  The maximum time `func` is allowed to be delayed before it's invoked.
 * @param {boolean} [options.trailing=true]
 *  Specify invoking on the trailing edge of the timeout.
 * @returns {Function} Returns the new debounced function.
 * @example
 *
 * // Avoid costly calculations while the window size is in flux.
 * jQuery(window).on('resize', _.debounce(calculateLayout, 150));
 *
 * // Invoke `sendMail` when clicked, debouncing subsequent calls.
 * jQuery(element).on('click', _.debounce(sendMail, 300, {
 *   'leading': true,
 *   'trailing': false
 * }));
 *
 * // Ensure `batchLog` is invoked once after 1 second of debounced calls.
 * var debounced = _.debounce(batchLog, 250, { 'maxWait': 1000 });
 * var source = new EventSource('/stream');
 * jQuery(source).on('message', debounced);
 *
 * // Cancel the trailing debounced invocation.
 * jQuery(window).on('popstate', debounced.cancel);
 */
function debounce(func, wait, options) {
  var lastArgs,
      lastThis,
      maxWait,
      result,
      timerId,
      lastCallTime,
      lastInvokeTime = 0,
      leading = false,
      maxing = false,
      trailing = true;

  if (typeof func != 'function') {
    throw new TypeError(FUNC_ERROR_TEXT);
  }
  wait = toNumber(wait) || 0;
  if (isObject(options)) {
    leading = !!options.leading;
    maxing = 'maxWait' in options;
    maxWait = maxing ? nativeMax(toNumber(options.maxWait) || 0, wait) : maxWait;
    trailing = 'trailing' in options ? !!options.trailing : trailing;
  }

  function invokeFunc(time) {
    var args = lastArgs,
        thisArg = lastThis;

    lastArgs = lastThis = undefined;
    lastInvokeTime = time;
    result = func.apply(thisArg, args);
    return result;
  }

  function leadingEdge(time) {
    // Reset any `maxWait` timer.
    lastInvokeTime = time;
    // Start the timer for the trailing edge.
    timerId = setTimeout(timerExpired, wait);
    // Invoke the leading edge.
    return leading ? invokeFunc(time) : result;
  }

  function remainingWait(time) {
    var timeSinceLastCall = time - lastCallTime,
        timeSinceLastInvoke = time - lastInvokeTime,
        result = wait - timeSinceLastCall;

    return maxing ? nativeMin(result, maxWait - timeSinceLastInvoke) : result;
  }

  function shouldInvoke(time) {
    var timeSinceLastCall = time - lastCallTime,
        timeSinceLastInvoke = time - lastInvokeTime;

    // Either this is the first call, activity has stopped and we're at the
    // trailing edge, the system time has gone backwards and we're treating
    // it as the trailing edge, or we've hit the `maxWait` limit.
    return (lastCallTime === undefined || (timeSinceLastCall >= wait) ||
      (timeSinceLastCall < 0) || (maxing && timeSinceLastInvoke >= maxWait));
  }

  function timerExpired() {
    var time = now();
    if (shouldInvoke(time)) {
      return trailingEdge(time);
    }
    // Restart the timer.
    timerId = setTimeout(timerExpired, remainingWait(time));
  }

  function trailingEdge(time) {
    timerId = undefined;

    // Only invoke if we have `lastArgs` which means `func` has been
    // debounced at least once.
    if (trailing && lastArgs) {
      return invokeFunc(time);
    }
    lastArgs = lastThis = undefined;
    return result;
  }

  function cancel() {
    if (timerId !== undefined) {
      clearTimeout(timerId);
    }
    lastInvokeTime = 0;
    lastArgs = lastCallTime = lastThis = timerId = undefined;
  }

  function flush() {
    return timerId === undefined ? result : trailingEdge(now());
  }

  function debounced() {
    var time = now(),
        isInvoking = shouldInvoke(time);

    lastArgs = arguments;
    lastThis = this;
    lastCallTime = time;

    if (isInvoking) {
      if (timerId === undefined) {
        return leadingEdge(lastCallTime);
      }
      if (maxing) {
        // Handle invocations in a tight loop.
        timerId = setTimeout(timerExpired, wait);
        return invokeFunc(lastCallTime);
      }
    }
    if (timerId === undefined) {
      timerId = setTimeout(timerExpired, wait);
    }
    return result;
  }
  debounced.cancel = cancel;
  debounced.flush = flush;
  return debounced;
}

/**
 * Checks if `value` is the
 * [language type](http://www.ecma-international.org/ecma-262/7.0/#sec-ecmascript-language-types)
 * of `Object`. (e.g. arrays, functions, objects, regexes, `new Number(0)`, and `new String('')`)
 *
 * @static
 * @memberOf _
 * @since 0.1.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is an object, else `false`.
 * @example
 *
 * _.isObject({});
 * // => true
 *
 * _.isObject([1, 2, 3]);
 * // => true
 *
 * _.isObject(_.noop);
 * // => true
 *
 * _.isObject(null);
 * // => false
 */
function isObject(value) {
  var type = typeof value;
  return !!value && (type == 'object' || type == 'function');
}

/**
 * Checks if `value` is object-like. A value is object-like if it's not `null`
 * and has a `typeof` result of "object".
 *
 * @static
 * @memberOf _
 * @since 4.0.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is object-like, else `false`.
 * @example
 *
 * _.isObjectLike({});
 * // => true
 *
 * _.isObjectLike([1, 2, 3]);
 * // => true
 *
 * _.isObjectLike(_.noop);
 * // => false
 *
 * _.isObjectLike(null);
 * // => false
 */
function isObjectLike(value) {
  return !!value && typeof value == 'object';
}

/**
 * Checks if `value` is classified as a `Symbol` primitive or object.
 *
 * @static
 * @memberOf _
 * @since 4.0.0
 * @category Lang
 * @param {*} value The value to check.
 * @returns {boolean} Returns `true` if `value` is a symbol, else `false`.
 * @example
 *
 * _.isSymbol(Symbol.iterator);
 * // => true
 *
 * _.isSymbol('abc');
 * // => false
 */
function isSymbol(value) {
  return typeof value == 'symbol' ||
    (isObjectLike(value) && objectToString.call(value) == symbolTag);
}

/**
 * Converts `value` to a number.
 *
 * @static
 * @memberOf _
 * @since 4.0.0
 * @category Lang
 * @param {*} value The value to process.
 * @returns {number} Returns the number.
 * @example
 *
 * _.toNumber(3.2);
 * // => 3.2
 *
 * _.toNumber(Number.MIN_VALUE);
 * // => 5e-324
 *
 * _.toNumber(Infinity);
 * // => Infinity
 *
 * _.toNumber('3.2');
 * // => 3.2
 */
function toNumber(value) {
  if (typeof value == 'number') {
    return value;
  }
  if (isSymbol(value)) {
    return NAN;
  }
  if (isObject(value)) {
    var other = typeof value.valueOf == 'function' ? value.valueOf() : value;
    value = isObject(other) ? (other + '') : other;
  }
  if (typeof value != 'string') {
    return value === 0 ? value : +value;
  }
  value = value.replace(reTrim, '');
  var isBinary = reIsBinary.test(value);
  return (isBinary || reIsOctal.test(value))
    ? freeParseInt(value.slice(2), isBinary ? 2 : 8)
    : (reIsBadHex.test(value) ? NAN : +value);
}

var lodash_debounce = debounce;

exports.default = lodash_debounce;


},{"../../_virtual/_commonjsHelpers.js":35}],50:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/*! *****************************************************************************
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
***************************************************************************** */
function t(t,n){var e="function"==typeof Symbol&&t[Symbol.iterator];if(!e)return t;var r,o,i=e.call(t),a=[];try{for(;(void 0===n||n-- >0)&&!(r=i.next()).done;)a.push(r.value);}catch(t){o={error:t};}finally{try{r&&!r.done&&(e=i.return)&&e.call(i);}finally{if(o)throw o.error}}return a}exports.InterpreterStatus = void 0;!function(t){t[t.NotStarted=0]="NotStarted",t[t.Running=1]="Running",t[t.Stopped=2]="Stopped";}(exports.InterpreterStatus||(exports.InterpreterStatus={}));var e={type:"xstate.init"};function r(t){return void 0===t?[]:[].concat(t)}function o(t){return {type:"xstate.assign",assignment:t}}function i(t,n){return "string"==typeof(t="string"==typeof t&&n&&n[t]?n[t]:t)?{type:t}:"function"==typeof t?{type:t.name,exec:t}:t}function a(t){return function(n){return t===n}}function u(t){return "string"==typeof t?{type:t}:t}function c(t,n){return {value:t,context:n,actions:[],changed:!1,matches:a(t)}}function f(t,n,e){var r=n,o=!1;return [t.filter((function(t){if("xstate.assign"===t.type){o=!0;var n=Object.assign({},r);return "function"==typeof t.assignment?n=t.assignment(r,e):Object.keys(t.assignment).forEach((function(o){n[o]="function"==typeof t.assignment[o]?t.assignment[o](r,e):t.assignment[o];})),r=n,!1}return !0})),r,o]}function s(n,o){void 0===o&&(o={});var s=t(f(r(n.states[n.initial].entry).map((function(t){return i(t,o.actions)})),n.context,e),2),l=s[0],v=s[1],y={config:n,_options:o,initialState:{value:n.initial,actions:l,context:v,matches:a(n.initial)},transition:function(e,o){var s,l,v="string"==typeof e?{value:e,context:n.context}:e,p=v.value,g=v.context,d=u(o),x=n.states[p];if(x.on){var m=r(x.on[d.type]);try{for(var h=function(t){var n="function"==typeof Symbol&&Symbol.iterator,e=n&&t[n],r=0;if(e)return e.call(t);if(t&&"number"==typeof t.length)return {next:function(){return t&&r>=t.length&&(t=void 0),{value:t&&t[r++],done:!t}}};throw new TypeError(n?"Object is not iterable.":"Symbol.iterator is not defined.")}(m),b=h.next();!b.done;b=h.next()){var S=b.value;if(void 0===S)return c(p,g);var w="string"==typeof S?{target:S}:S,j=w.target,E=w.actions,R=void 0===E?[]:E,N=w.cond,O=void 0===N?function(){return !0}:N,_=void 0===j,k=null!=j?j:p,T=n.states[k];if(O(g,d)){var q=t(f((_?r(R):[].concat(x.exit,R,T.entry).filter((function(t){return t}))).map((function(t){return i(t,y._options.actions)})),g,d),3),z=q[0],A=q[1],B=q[2],C=null!=j?j:p;return {value:C,context:A,actions:z,changed:j!==p||z.length>0||B,matches:a(C)}}}}catch(t){s={error:t};}finally{try{b&&!b.done&&(l=h.return)&&l.call(h);}finally{if(s)throw s.error}}}return c(p,g)}};return y}var l=function(t,n){return t.actions.forEach((function(e){var r=e.exec;return r&&r(t.context,n)}))};function v(t){var r=t.initialState,o=exports.InterpreterStatus.NotStarted,i=new Set,c={_machine:t,send:function(e){o===exports.InterpreterStatus.Running&&(r=t.transition(r,e),l(r,u(e)),i.forEach((function(t){return t(r)})));},subscribe:function(t){return i.add(t),t(r),{unsubscribe:function(){return i.delete(t)}}},start:function(i){if(i){var u="object"==typeof i?i:{context:t.config.context,value:i};r={value:u.value,actions:[],context:u.context,matches:a(u.value)};}return o=exports.InterpreterStatus.Running,l(r,e),c},stop:function(){return o=exports.InterpreterStatus.Stopped,i.clear(),c},get state(){return r},get status(){return o}};return c}

exports.assign = o;
exports.createMachine = s;
exports.interpret = v;


},{}],51:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/*
 * base64-arraybuffer 1.0.1 <https://github.com/niklasvh/base64-arraybuffer>
 * Copyright (c) 2021 Niklas von Hertzen <https://hertzen.com>
 * Released under MIT License
 */
var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
// Use a lookup table to find the index.
var lookup = typeof Uint8Array === 'undefined' ? [] : new Uint8Array(256);
for (var i = 0; i < chars.length; i++) {
    lookup[chars.charCodeAt(i)] = i;
}
var encode = function (arraybuffer) {
    var bytes = new Uint8Array(arraybuffer), i, len = bytes.length, base64 = '';
    for (i = 0; i < len; i += 3) {
        base64 += chars[bytes[i] >> 2];
        base64 += chars[((bytes[i] & 3) << 4) | (bytes[i + 1] >> 4)];
        base64 += chars[((bytes[i + 1] & 15) << 2) | (bytes[i + 2] >> 6)];
        base64 += chars[bytes[i + 2] & 63];
    }
    if (len % 3 === 2) {
        base64 = base64.substring(0, base64.length - 1) + '=';
    }
    else if (len % 3 === 1) {
        base64 = base64.substring(0, base64.length - 2) + '==';
    }
    return base64;
};
var decode = function (base64) {
    var bufferLength = base64.length * 0.75, len = base64.length, i, p = 0, encoded1, encoded2, encoded3, encoded4;
    if (base64[base64.length - 1] === '=') {
        bufferLength--;
        if (base64[base64.length - 2] === '=') {
            bufferLength--;
        }
    }
    var arraybuffer = new ArrayBuffer(bufferLength), bytes = new Uint8Array(arraybuffer);
    for (i = 0; i < len; i += 4) {
        encoded1 = lookup[base64.charCodeAt(i)];
        encoded2 = lookup[base64.charCodeAt(i + 1)];
        encoded3 = lookup[base64.charCodeAt(i + 2)];
        encoded4 = lookup[base64.charCodeAt(i + 3)];
        bytes[p++] = (encoded1 << 2) | (encoded2 >> 4);
        bytes[p++] = ((encoded2 & 15) << 4) | (encoded3 >> 2);
        bytes[p++] = ((encoded3 & 3) << 6) | (encoded4 & 63);
    }
    return arraybuffer;
};

exports.decode = decode;
exports.encode = encode;


},{}],52:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// DEFLATE is a complex format; to read this code, you should probably check the RFC first:

// aliases for shorter compressed code (most minifers don't do this)
var u8 = Uint8Array, u16 = Uint16Array, u32 = Uint32Array;
// fixed length extra bits
var fleb = new u8([0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0, /* unused */ 0, 0, /* impossible */ 0]);
// fixed distance extra bits
// see fleb note
var fdeb = new u8([0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13, /* unused */ 0, 0]);
// code length index map
var clim = new u8([16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]);
// get base, reverse index map from extra bits
var freb = function (eb, start) {
    var b = new u16(31);
    for (var i = 0; i < 31; ++i) {
        b[i] = start += 1 << eb[i - 1];
    }
    // numbers here are at max 18 bits
    var r = new u32(b[30]);
    for (var i = 1; i < 30; ++i) {
        for (var j = b[i]; j < b[i + 1]; ++j) {
            r[j] = ((j - b[i]) << 5) | i;
        }
    }
    return [b, r];
};
var _a = freb(fleb, 2), fl = _a[0], revfl = _a[1];
// we can ignore the fact that the other numbers are wrong; they never happen anyway
fl[28] = 258, revfl[258] = 28;
var _b = freb(fdeb, 0), fd = _b[0], revfd = _b[1];
// map of value to reverse (assuming 16 bits)
var rev = new u16(32768);
for (var i = 0; i < 32768; ++i) {
    // reverse table algorithm from SO
    var x = ((i & 0xAAAA) >>> 1) | ((i & 0x5555) << 1);
    x = ((x & 0xCCCC) >>> 2) | ((x & 0x3333) << 2);
    x = ((x & 0xF0F0) >>> 4) | ((x & 0x0F0F) << 4);
    rev[i] = (((x & 0xFF00) >>> 8) | ((x & 0x00FF) << 8)) >>> 1;
}
// create huffman tree from u8 "map": index -> code length for code index
// mb (max bits) must be at most 15
// TODO: optimize/split up?
var hMap = (function (cd, mb, r) {
    var s = cd.length;
    // index
    var i = 0;
    // u16 "map": index -> # of codes with bit length = index
    var l = new u16(mb);
    // length of cd must be 288 (total # of codes)
    for (; i < s; ++i)
        ++l[cd[i] - 1];
    // u16 "map": index -> minimum code for bit length = index
    var le = new u16(mb);
    for (i = 0; i < mb; ++i) {
        le[i] = (le[i - 1] + l[i - 1]) << 1;
    }
    var co;
    if (r) {
        // u16 "map": index -> number of actual bits, symbol for code
        co = new u16(1 << mb);
        // bits to remove for reverser
        var rvb = 15 - mb;
        for (i = 0; i < s; ++i) {
            // ignore 0 lengths
            if (cd[i]) {
                // num encoding both symbol and bits read
                var sv = (i << 4) | cd[i];
                // free bits
                var r_1 = mb - cd[i];
                // start value
                var v = le[cd[i] - 1]++ << r_1;
                // m is end value
                for (var m = v | ((1 << r_1) - 1); v <= m; ++v) {
                    // every 16 bit value starting with the code yields the same result
                    co[rev[v] >>> rvb] = sv;
                }
            }
        }
    }
    else {
        co = new u16(s);
        for (i = 0; i < s; ++i)
            co[i] = rev[le[cd[i] - 1]++] >>> (15 - cd[i]);
    }
    return co;
});
// fixed length tree
var flt = new u8(288);
for (var i = 0; i < 144; ++i)
    flt[i] = 8;
for (var i = 144; i < 256; ++i)
    flt[i] = 9;
for (var i = 256; i < 280; ++i)
    flt[i] = 7;
for (var i = 280; i < 288; ++i)
    flt[i] = 8;
// fixed distance tree
var fdt = new u8(32);
for (var i = 0; i < 32; ++i)
    fdt[i] = 5;
// fixed length map
var flm = /*#__PURE__*/ hMap(flt, 9, 0), flrm = /*#__PURE__*/ hMap(flt, 9, 1);
// fixed distance map
var fdm = /*#__PURE__*/ hMap(fdt, 5, 0), fdrm = /*#__PURE__*/ hMap(fdt, 5, 1);
// find max of array
var max = function (a) {
    var m = a[0];
    for (var i = 1; i < a.length; ++i) {
        if (a[i] > m)
            m = a[i];
    }
    return m;
};
// read d, starting at bit p and mask with m
var bits = function (d, p, m) {
    var o = (p / 8) >> 0;
    return ((d[o] | (d[o + 1] << 8)) >>> (p & 7)) & m;
};
// read d, starting at bit p continuing for at least 16 bits
var bits16 = function (d, p) {
    var o = (p / 8) >> 0;
    return ((d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)) >>> (p & 7));
};
// get end of byte
var shft = function (p) { return ((p / 8) >> 0) + (p & 7 && 1); };
// typed array slice - allows garbage collector to free original reference,
// while being more compatible than .slice
var slc = function (v, s, e) {
    if (s == null || s < 0)
        s = 0;
    if (e == null || e > v.length)
        e = v.length;
    // can't use .constructor in case user-supplied
    var n = new (v instanceof u16 ? u16 : v instanceof u32 ? u32 : u8)(e - s);
    n.set(v.subarray(s, e));
    return n;
};
// expands raw DEFLATE data
var inflt = function (dat, buf, st) {
    // source length
    var sl = dat.length;
    // have to estimate size
    var noBuf = !buf || st;
    // no state
    var noSt = !st || st.i;
    if (!st)
        st = {};
    // Assumes roughly 33% compression ratio average
    if (!buf)
        buf = new u8(sl * 3);
    // ensure buffer can fit at least l elements
    var cbuf = function (l) {
        var bl = buf.length;
        // need to increase size to fit
        if (l > bl) {
            // Double or set to necessary, whichever is greater
            var nbuf = new u8(Math.max(bl * 2, l));
            nbuf.set(buf);
            buf = nbuf;
        }
    };
    //  last chunk         bitpos           bytes
    var final = st.f || 0, pos = st.p || 0, bt = st.b || 0, lm = st.l, dm = st.d, lbt = st.m, dbt = st.n;
    // total bits
    var tbts = sl * 8;
    do {
        if (!lm) {
            // BFINAL - this is only 1 when last chunk is next
            st.f = final = bits(dat, pos, 1);
            // type: 0 = no compression, 1 = fixed huffman, 2 = dynamic huffman
            var type = bits(dat, pos + 1, 3);
            pos += 3;
            if (!type) {
                // go to end of byte boundary
                var s = shft(pos) + 4, l = dat[s - 4] | (dat[s - 3] << 8), t = s + l;
                if (t > sl) {
                    if (noSt)
                        throw 'unexpected EOF';
                    break;
                }
                // ensure size
                if (noBuf)
                    cbuf(bt + l);
                // Copy over uncompressed data
                buf.set(dat.subarray(s, t), bt);
                // Get new bitpos, update byte count
                st.b = bt += l, st.p = pos = t * 8;
                continue;
            }
            else if (type == 1)
                lm = flrm, dm = fdrm, lbt = 9, dbt = 5;
            else if (type == 2) {
                //  literal                            lengths
                var hLit = bits(dat, pos, 31) + 257, hcLen = bits(dat, pos + 10, 15) + 4;
                var tl = hLit + bits(dat, pos + 5, 31) + 1;
                pos += 14;
                // length+distance tree
                var ldt = new u8(tl);
                // code length tree
                var clt = new u8(19);
                for (var i = 0; i < hcLen; ++i) {
                    // use index map to get real code
                    clt[clim[i]] = bits(dat, pos + i * 3, 7);
                }
                pos += hcLen * 3;
                // code lengths bits
                var clb = max(clt), clbmsk = (1 << clb) - 1;
                if (!noSt && pos + tl * (clb + 7) > tbts)
                    break;
                // code lengths map
                var clm = hMap(clt, clb, 1);
                for (var i = 0; i < tl;) {
                    var r = clm[bits(dat, pos, clbmsk)];
                    // bits read
                    pos += r & 15;
                    // symbol
                    var s = r >>> 4;
                    // code length to copy
                    if (s < 16) {
                        ldt[i++] = s;
                    }
                    else {
                        //  copy   count
                        var c = 0, n = 0;
                        if (s == 16)
                            n = 3 + bits(dat, pos, 3), pos += 2, c = ldt[i - 1];
                        else if (s == 17)
                            n = 3 + bits(dat, pos, 7), pos += 3;
                        else if (s == 18)
                            n = 11 + bits(dat, pos, 127), pos += 7;
                        while (n--)
                            ldt[i++] = c;
                    }
                }
                //    length tree                 distance tree
                var lt = ldt.subarray(0, hLit), dt = ldt.subarray(hLit);
                // max length bits
                lbt = max(lt);
                // max dist bits
                dbt = max(dt);
                lm = hMap(lt, lbt, 1);
                dm = hMap(dt, dbt, 1);
            }
            else
                throw 'invalid block type';
            if (pos > tbts)
                throw 'unexpected EOF';
        }
        // Make sure the buffer can hold this + the largest possible addition
        // Maximum chunk size (practically, theoretically infinite) is 2^17;
        if (noBuf)
            cbuf(bt + 131072);
        var lms = (1 << lbt) - 1, dms = (1 << dbt) - 1;
        var mxa = lbt + dbt + 18;
        while (noSt || pos + mxa < tbts) {
            // bits read, code
            var c = lm[bits16(dat, pos) & lms], sym = c >>> 4;
            pos += c & 15;
            if (pos > tbts)
                throw 'unexpected EOF';
            if (!c)
                throw 'invalid length/literal';
            if (sym < 256)
                buf[bt++] = sym;
            else if (sym == 256) {
                lm = null;
                break;
            }
            else {
                var add = sym - 254;
                // no extra bits needed if less
                if (sym > 264) {
                    // index
                    var i = sym - 257, b = fleb[i];
                    add = bits(dat, pos, (1 << b) - 1) + fl[i];
                    pos += b;
                }
                // dist
                var d = dm[bits16(dat, pos) & dms], dsym = d >>> 4;
                if (!d)
                    throw 'invalid distance';
                pos += d & 15;
                var dt = fd[dsym];
                if (dsym > 3) {
                    var b = fdeb[dsym];
                    dt += bits16(dat, pos) & ((1 << b) - 1), pos += b;
                }
                if (pos > tbts)
                    throw 'unexpected EOF';
                if (noBuf)
                    cbuf(bt + 131072);
                var end = bt + add;
                for (; bt < end; bt += 4) {
                    buf[bt] = buf[bt - dt];
                    buf[bt + 1] = buf[bt + 1 - dt];
                    buf[bt + 2] = buf[bt + 2 - dt];
                    buf[bt + 3] = buf[bt + 3 - dt];
                }
                bt = end;
            }
        }
        st.l = lm, st.p = pos, st.b = bt;
        if (lm)
            final = 1, st.m = lbt, st.d = dm, st.n = dbt;
    } while (!final);
    return bt == buf.length ? buf : slc(buf, 0, bt);
};
// starting at p, write the minimum number of bits that can hold v to d
var wbits = function (d, p, v) {
    v <<= p & 7;
    var o = (p / 8) >> 0;
    d[o] |= v;
    d[o + 1] |= v >>> 8;
};
// starting at p, write the minimum number of bits (>8) that can hold v to d
var wbits16 = function (d, p, v) {
    v <<= p & 7;
    var o = (p / 8) >> 0;
    d[o] |= v;
    d[o + 1] |= v >>> 8;
    d[o + 2] |= v >>> 16;
};
// creates code lengths from a frequency table
var hTree = function (d, mb) {
    // Need extra info to make a tree
    var t = [];
    for (var i = 0; i < d.length; ++i) {
        if (d[i])
            t.push({ s: i, f: d[i] });
    }
    var s = t.length;
    var t2 = t.slice();
    if (!s)
        return [new u8(0), 0];
    if (s == 1) {
        var v = new u8(t[0].s + 1);
        v[t[0].s] = 1;
        return [v, 1];
    }
    t.sort(function (a, b) { return a.f - b.f; });
    // after i2 reaches last ind, will be stopped
    // freq must be greater than largest possible number of symbols
    t.push({ s: -1, f: 25001 });
    var l = t[0], r = t[1], i0 = 0, i1 = 1, i2 = 2;
    t[0] = { s: -1, f: l.f + r.f, l: l, r: r };
    // efficient algorithm from UZIP.js
    // i0 is lookbehind, i2 is lookahead - after processing two low-freq
    // symbols that combined have high freq, will start processing i2 (high-freq,
    // non-composite) symbols instead
    // see https://reddit.com/r/photopea/comments/ikekht/uzipjs_questions/
    while (i1 != s - 1) {
        l = t[t[i0].f < t[i2].f ? i0++ : i2++];
        r = t[i0 != i1 && t[i0].f < t[i2].f ? i0++ : i2++];
        t[i1++] = { s: -1, f: l.f + r.f, l: l, r: r };
    }
    var maxSym = t2[0].s;
    for (var i = 1; i < s; ++i) {
        if (t2[i].s > maxSym)
            maxSym = t2[i].s;
    }
    // code lengths
    var tr = new u16(maxSym + 1);
    // max bits in tree
    var mbt = ln(t[i1 - 1], tr, 0);
    if (mbt > mb) {
        // more algorithms from UZIP.js
        // TODO: find out how this code works (debt)
        //  ind    debt
        var i = 0, dt = 0;
        //    left            cost
        var lft = mbt - mb, cst = 1 << lft;
        t2.sort(function (a, b) { return tr[b.s] - tr[a.s] || a.f - b.f; });
        for (; i < s; ++i) {
            var i2_1 = t2[i].s;
            if (tr[i2_1] > mb) {
                dt += cst - (1 << (mbt - tr[i2_1]));
                tr[i2_1] = mb;
            }
            else
                break;
        }
        dt >>>= lft;
        while (dt > 0) {
            var i2_2 = t2[i].s;
            if (tr[i2_2] < mb)
                dt -= 1 << (mb - tr[i2_2]++ - 1);
            else
                ++i;
        }
        for (; i >= 0 && dt; --i) {
            var i2_3 = t2[i].s;
            if (tr[i2_3] == mb) {
                --tr[i2_3];
                ++dt;
            }
        }
        mbt = mb;
    }
    return [new u8(tr), mbt];
};
// get the max length and assign length codes
var ln = function (n, l, d) {
    return n.s == -1
        ? Math.max(ln(n.l, l, d + 1), ln(n.r, l, d + 1))
        : (l[n.s] = d);
};
// length codes generation
var lc = function (c) {
    var s = c.length;
    // Note that the semicolon was intentional
    while (s && !c[--s])
        ;
    var cl = new u16(++s);
    //  ind      num         streak
    var cli = 0, cln = c[0], cls = 1;
    var w = function (v) { cl[cli++] = v; };
    for (var i = 1; i <= s; ++i) {
        if (c[i] == cln && i != s)
            ++cls;
        else {
            if (!cln && cls > 2) {
                for (; cls > 138; cls -= 138)
                    w(32754);
                if (cls > 2) {
                    w(cls > 10 ? ((cls - 11) << 5) | 28690 : ((cls - 3) << 5) | 12305);
                    cls = 0;
                }
            }
            else if (cls > 3) {
                w(cln), --cls;
                for (; cls > 6; cls -= 6)
                    w(8304);
                if (cls > 2)
                    w(((cls - 3) << 5) | 8208), cls = 0;
            }
            while (cls--)
                w(cln);
            cls = 1;
            cln = c[i];
        }
    }
    return [cl.subarray(0, cli), s];
};
// calculate the length of output from tree, code lengths
var clen = function (cf, cl) {
    var l = 0;
    for (var i = 0; i < cl.length; ++i)
        l += cf[i] * cl[i];
    return l;
};
// writes a fixed block
// returns the new bit pos
var wfblk = function (out, pos, dat) {
    // no need to write 00 as type: TypedArray defaults to 0
    var s = dat.length;
    var o = shft(pos + 2);
    out[o] = s & 255;
    out[o + 1] = s >>> 8;
    out[o + 2] = out[o] ^ 255;
    out[o + 3] = out[o + 1] ^ 255;
    for (var i = 0; i < s; ++i)
        out[o + i + 4] = dat[i];
    return (o + 4 + s) * 8;
};
// writes a block
var wblk = function (dat, out, final, syms, lf, df, eb, li, bs, bl, p) {
    wbits(out, p++, final);
    ++lf[256];
    var _a = hTree(lf, 15), dlt = _a[0], mlb = _a[1];
    var _b = hTree(df, 15), ddt = _b[0], mdb = _b[1];
    var _c = lc(dlt), lclt = _c[0], nlc = _c[1];
    var _d = lc(ddt), lcdt = _d[0], ndc = _d[1];
    var lcfreq = new u16(19);
    for (var i = 0; i < lclt.length; ++i)
        lcfreq[lclt[i] & 31]++;
    for (var i = 0; i < lcdt.length; ++i)
        lcfreq[lcdt[i] & 31]++;
    var _e = hTree(lcfreq, 7), lct = _e[0], mlcb = _e[1];
    var nlcc = 19;
    for (; nlcc > 4 && !lct[clim[nlcc - 1]]; --nlcc)
        ;
    var flen = (bl + 5) << 3;
    var ftlen = clen(lf, flt) + clen(df, fdt) + eb;
    var dtlen = clen(lf, dlt) + clen(df, ddt) + eb + 14 + 3 * nlcc + clen(lcfreq, lct) + (2 * lcfreq[16] + 3 * lcfreq[17] + 7 * lcfreq[18]);
    if (flen <= ftlen && flen <= dtlen)
        return wfblk(out, p, dat.subarray(bs, bs + bl));
    var lm, ll, dm, dl;
    wbits(out, p, 1 + (dtlen < ftlen)), p += 2;
    if (dtlen < ftlen) {
        lm = hMap(dlt, mlb, 0), ll = dlt, dm = hMap(ddt, mdb, 0), dl = ddt;
        var llm = hMap(lct, mlcb, 0);
        wbits(out, p, nlc - 257);
        wbits(out, p + 5, ndc - 1);
        wbits(out, p + 10, nlcc - 4);
        p += 14;
        for (var i = 0; i < nlcc; ++i)
            wbits(out, p + 3 * i, lct[clim[i]]);
        p += 3 * nlcc;
        var lcts = [lclt, lcdt];
        for (var it = 0; it < 2; ++it) {
            var clct = lcts[it];
            for (var i = 0; i < clct.length; ++i) {
                var len = clct[i] & 31;
                wbits(out, p, llm[len]), p += lct[len];
                if (len > 15)
                    wbits(out, p, (clct[i] >>> 5) & 127), p += clct[i] >>> 12;
            }
        }
    }
    else {
        lm = flm, ll = flt, dm = fdm, dl = fdt;
    }
    for (var i = 0; i < li; ++i) {
        if (syms[i] > 255) {
            var len = (syms[i] >>> 18) & 31;
            wbits16(out, p, lm[len + 257]), p += ll[len + 257];
            if (len > 7)
                wbits(out, p, (syms[i] >>> 23) & 31), p += fleb[len];
            var dst = syms[i] & 31;
            wbits16(out, p, dm[dst]), p += dl[dst];
            if (dst > 3)
                wbits16(out, p, (syms[i] >>> 5) & 8191), p += fdeb[dst];
        }
        else {
            wbits16(out, p, lm[syms[i]]), p += ll[syms[i]];
        }
    }
    wbits16(out, p, lm[256]);
    return p + ll[256];
};
// deflate options (nice << 13) | chain
var deo = /*#__PURE__*/ new u32([65540, 131080, 131088, 131104, 262176, 1048704, 1048832, 2114560, 2117632]);
// empty
var et = /*#__PURE__*/ new u8(0);
// compresses data into a raw DEFLATE buffer
var dflt = function (dat, lvl, plvl, pre, post, lst) {
    var s = dat.length;
    var o = new u8(pre + s + 5 * (1 + Math.floor(s / 7000)) + post);
    // writing to this writes to the output buffer
    var w = o.subarray(pre, o.length - post);
    var pos = 0;
    if (!lvl || s < 8) {
        for (var i = 0; i <= s; i += 65535) {
            // end
            var e = i + 65535;
            if (e < s) {
                // write full block
                pos = wfblk(w, pos, dat.subarray(i, e));
            }
            else {
                // write final block
                w[i] = lst;
                pos = wfblk(w, pos, dat.subarray(i, s));
            }
        }
    }
    else {
        var opt = deo[lvl - 1];
        var n = opt >>> 13, c = opt & 8191;
        var msk_1 = (1 << plvl) - 1;
        //    prev 2-byte val map    curr 2-byte val map
        var prev = new u16(32768), head = new u16(msk_1 + 1);
        var bs1_1 = Math.ceil(plvl / 3), bs2_1 = 2 * bs1_1;
        var hsh = function (i) { return (dat[i] ^ (dat[i + 1] << bs1_1) ^ (dat[i + 2] << bs2_1)) & msk_1; };
        // 24576 is an arbitrary number of maximum symbols per block
        // 424 buffer for last block
        var syms = new u32(25000);
        // length/literal freq   distance freq
        var lf = new u16(288), df = new u16(32);
        //  l/lcnt  exbits  index  l/lind  waitdx  bitpos
        var lc_1 = 0, eb = 0, i = 0, li = 0, wi = 0, bs = 0;
        for (; i < s; ++i) {
            // hash value
            var hv = hsh(i);
            // index mod 32768
            var imod = i & 32767;
            // previous index with this value
            var pimod = head[hv];
            prev[imod] = pimod;
            head[hv] = imod;
            // We always should modify head and prev, but only add symbols if
            // this data is not yet processed ("wait" for wait index)
            if (wi <= i) {
                // bytes remaining
                var rem = s - i;
                if ((lc_1 > 7000 || li > 24576) && rem > 423) {
                    pos = wblk(dat, w, 0, syms, lf, df, eb, li, bs, i - bs, pos);
                    li = lc_1 = eb = 0, bs = i;
                    for (var j = 0; j < 286; ++j)
                        lf[j] = 0;
                    for (var j = 0; j < 30; ++j)
                        df[j] = 0;
                }
                //  len    dist   chain
                var l = 2, d = 0, ch_1 = c, dif = (imod - pimod) & 32767;
                if (rem > 2 && hv == hsh(i - dif)) {
                    var maxn = Math.min(n, rem) - 1;
                    var maxd = Math.min(32767, i);
                    // max possible length
                    // not capped at dif because decompressors implement "rolling" index population
                    var ml = Math.min(258, rem);
                    while (dif <= maxd && --ch_1 && imod != pimod) {
                        if (dat[i + l] == dat[i + l - dif]) {
                            var nl = 0;
                            for (; nl < ml && dat[i + nl] == dat[i + nl - dif]; ++nl)
                                ;
                            if (nl > l) {
                                l = nl, d = dif;
                                // break out early when we reach "nice" (we are satisfied enough)
                                if (nl > maxn)
                                    break;
                                // now, find the rarest 2-byte sequence within this
                                // length of literals and search for that instead.
                                // Much faster than just using the start
                                var mmd = Math.min(dif, nl - 2);
                                var md = 0;
                                for (var j = 0; j < mmd; ++j) {
                                    var ti = (i - dif + j + 32768) & 32767;
                                    var pti = prev[ti];
                                    var cd = (ti - pti + 32768) & 32767;
                                    if (cd > md)
                                        md = cd, pimod = ti;
                                }
                            }
                        }
                        // check the previous match
                        imod = pimod, pimod = prev[imod];
                        dif += (imod - pimod + 32768) & 32767;
                    }
                }
                // d will be nonzero only when a match was found
                if (d) {
                    // store both dist and len data in one Uint32
                    // Make sure this is recognized as a len/dist with 28th bit (2^28)
                    syms[li++] = 268435456 | (revfl[l] << 18) | revfd[d];
                    var lin = revfl[l] & 31, din = revfd[d] & 31;
                    eb += fleb[lin] + fdeb[din];
                    ++lf[257 + lin];
                    ++df[din];
                    wi = i + l;
                    ++lc_1;
                }
                else {
                    syms[li++] = dat[i];
                    ++lf[dat[i]];
                }
            }
        }
        pos = wblk(dat, w, lst, syms, lf, df, eb, li, bs, i - bs, pos);
        // this is the easiest way to avoid needing to maintain state
        if (!lst)
            pos = wfblk(w, pos, et);
    }
    return slc(o, 0, pre + shft(pos) + post);
};
// Alder32
var adler = function () {
    var a = 1, b = 0;
    return {
        p: function (d) {
            // closures have awful performance
            var n = a, m = b;
            var l = d.length;
            for (var i = 0; i != l;) {
                var e = Math.min(i + 5552, l);
                for (; i < e; ++i)
                    n += d[i], m += n;
                n %= 65521, m %= 65521;
            }
            a = n, b = m;
        },
        d: function () { return ((a >>> 8) << 16 | (b & 255) << 8 | (b >>> 8)) + ((a & 255) << 23) * 2; }
    };
};
// deflate with opts
var dopt = function (dat, opt, pre, post, st) {
    return dflt(dat, opt.level == null ? 6 : opt.level, opt.mem == null ? Math.ceil(Math.max(8, Math.min(13, Math.log(dat.length))) * 1.5) : (12 + opt.mem), pre, post, !st);
};
// write bytes
var wbytes = function (d, b, v) {
    for (; v; ++b)
        d[b] = v, v >>>= 8;
};
// zlib header
var zlh = function (c, o) {
    var lv = o.level, fl = lv == 0 ? 0 : lv < 6 ? 1 : lv == 9 ? 3 : 2;
    c[0] = 120, c[1] = (fl << 6) | (fl ? (32 - 2 * fl) : 1);
};
// zlib valid
var zlv = function (d) {
    if ((d[0] & 15) != 8 || (d[0] >>> 4) > 7 || ((d[0] << 8 | d[1]) % 31))
        throw 'invalid zlib data';
    if (d[1] & 32)
        throw 'invalid zlib data: preset dictionaries not supported';
};
/**
 * Compress data with Zlib
 * @param data The data to compress
 * @param opts The compression options
 * @returns The zlib-compressed version of the data
 */
function zlibSync(data, opts) {
    if (opts === void 0) { opts = {}; }
    var a = adler();
    a.p(data);
    var d = dopt(data, opts, 2, 4);
    return zlh(d, opts), wbytes(d, d.length - 4, a.d()), d;
}
/**
 * Expands Zlib data
 * @param data The data to decompress
 * @param out Where to write the data. Saves memory if you know the decompressed size and provide an output buffer of that length.
 * @returns The decompressed version of the data
 */
function unzlibSync(data, out) {
    return inflt((zlv(data), data.subarray(2, -4)), out);
}
/**
 * Converts a string into a Uint8Array for use with compression/decompression methods
 * @param str The string to encode
 * @param latin1 Whether or not to interpret the data as Latin-1. This should
 *               not need to be true unless decoding a binary string.
 * @returns The string encoded in UTF-8/Latin-1 binary
 */
function strToU8(str, latin1) {
    var l = str.length;
    if (!latin1 && typeof TextEncoder != 'undefined')
        return new TextEncoder().encode(str);
    var ar = new u8(str.length + (str.length >>> 1));
    var ai = 0;
    var w = function (v) { ar[ai++] = v; };
    for (var i = 0; i < l; ++i) {
        if (ai + 5 > ar.length) {
            var n = new u8(ai + 8 + ((l - i) << 1));
            n.set(ar);
            ar = n;
        }
        var c = str.charCodeAt(i);
        if (c < 128 || latin1)
            w(c);
        else if (c < 2048)
            w(192 | (c >>> 6)), w(128 | (c & 63));
        else if (c > 55295 && c < 57344)
            c = 65536 + (c & 1023 << 10) | (str.charCodeAt(++i) & 1023),
                w(240 | (c >>> 18)), w(128 | ((c >>> 12) & 63)), w(128 | ((c >>> 6) & 63)), w(128 | (c & 63));
        else
            w(224 | (c >>> 12)), w(128 | ((c >>> 6) & 63)), w(128 | (c & 63));
    }
    return slc(ar, 0, ai);
}
/**
 * Converts a Uint8Array to a string
 * @param dat The data to decode to string
 * @param latin1 Whether or not to interpret the data as Latin-1. This should
 *               not need to be true unless encoding to binary string.
 * @returns The original UTF-8/Latin-1 string
 */
function strFromU8(dat, latin1) {
    var r = '';
    if (!latin1 && typeof TextDecoder != 'undefined')
        return new TextDecoder().decode(dat);
    for (var i = 0; i < dat.length;) {
        var c = dat[i++];
        if (c < 128 || latin1)
            r += String.fromCharCode(c);
        else if (c < 224)
            r += String.fromCharCode((c & 31) << 6 | (dat[i++] & 63));
        else if (c < 240)
            r += String.fromCharCode((c & 15) << 12 | (dat[i++] & 63) << 6 | (dat[i++] & 63));
        else
            c = ((c & 15) << 18 | (dat[i++] & 63) << 12 | (dat[i++] & 63) << 6 | (dat[i++] & 63)) - 65536,
                r += String.fromCharCode(55296 | (c >> 10), 56320 | (c & 1023));
    }
    return r;
}

exports.strFromU8 = strFromU8;
exports.strToU8 = strToU8;
exports.unzlibSync = unzlibSync;
exports.zlibSync = zlibSync;


},{}],53:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

//
// An event handler can take an optional event argument
// and should not return a value

// An array of all currently registered event handlers for a type

// A map of event types and their corresponding event handlers.

/** Mitt: Tiny (~200b) functional event emitter / pubsub.
 *  @name mitt
 *  @returns {Mitt}
 */
function mitt(all                 ) {
	all = all || Object.create(null);

	return {
		/**
		 * Register an event handler for the given type.
		 *
		 * @param  {String} type	Type of event to listen for, or `"*"` for all events
		 * @param  {Function} handler Function to call in response to given event
		 * @memberOf mitt
		 */
		on: function on(type        , handler              ) {
			(all[type] || (all[type] = [])).push(handler);
		},

		/**
		 * Remove an event handler for the given type.
		 *
		 * @param  {String} type	Type of event to unregister `handler` from, or `"*"`
		 * @param  {Function} handler Handler function to remove
		 * @memberOf mitt
		 */
		off: function off(type        , handler              ) {
			if (all[type]) {
				all[type].splice(all[type].indexOf(handler) >>> 0, 1);
			}
		},

		/**
		 * Invoke all handlers for the given type.
		 * If present, `"*"` handlers are invoked after type-matched handlers.
		 *
		 * @param {String} type  The event type to invoke
		 * @param {Any} [evt]  Any value (object is recommended and powerful), passed to each handler
		 * @memberOf mitt
		 */
		emit: function emit(type        , evt     ) {
			(all[type] || []).slice().map(function (handler) { handler(evt); });
			(all['*'] || []).slice().map(function (handler) { handler(type, evt); });
		}
	};
}

exports.default = mitt;


},{}],54:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

exports.NodeType = void 0;
(function (NodeType) {
    NodeType[NodeType["Document"] = 0] = "Document";
    NodeType[NodeType["DocumentType"] = 1] = "DocumentType";
    NodeType[NodeType["Element"] = 2] = "Element";
    NodeType[NodeType["Text"] = 3] = "Text";
    NodeType[NodeType["CDATA"] = 4] = "CDATA";
    NodeType[NodeType["Comment"] = 5] = "Comment";
})(exports.NodeType || (exports.NodeType = {}));

function isElement(n) {
    return n.nodeType === n.ELEMENT_NODE;
}
function isShadowRoot(n) {
    var _a;
    var host = (_a = n) === null || _a === void 0 ? void 0 : _a.host;
    return Boolean(host && host.shadowRoot && host.shadowRoot === n);
}
function maskInputValue(_a) {
    var maskInputOptions = _a.maskInputOptions, tagName = _a.tagName, type = _a.type, value = _a.value, maskInputFn = _a.maskInputFn;
    var text = value || '';
    if (maskInputOptions[tagName.toLowerCase()] ||
        maskInputOptions[type]) {
        if (maskInputFn) {
            text = maskInputFn(text);
        }
        else {
            text = '*'.repeat(text.length);
        }
    }
    return text;
}
var ORIGINAL_ATTRIBUTE_NAME = '__rrweb_original__';
function is2DCanvasBlank(canvas) {
    var ctx = canvas.getContext('2d');
    if (!ctx)
        return true;
    var chunkSize = 50;
    for (var x = 0; x < canvas.width; x += chunkSize) {
        for (var y = 0; y < canvas.height; y += chunkSize) {
            var getImageData = ctx.getImageData;
            var originalGetImageData = ORIGINAL_ATTRIBUTE_NAME in getImageData
                ? getImageData[ORIGINAL_ATTRIBUTE_NAME]
                : getImageData;
            var pixelBuffer = new Uint32Array(originalGetImageData.call(ctx, x, y, Math.min(chunkSize, canvas.width - x), Math.min(chunkSize, canvas.height - y)).data.buffer);
            if (pixelBuffer.some(function (pixel) { return pixel !== 0; }))
                return false;
        }
    }
    return true;
}

var _id = 1;
var tagNameRegex = new RegExp('[^a-z0-9-_:]');
var IGNORED_NODE = -2;
function genId() {
    return _id++;
}
function getValidTagName(element) {
    if (element instanceof HTMLFormElement) {
        return 'form';
    }
    var processedTagName = element.tagName.toLowerCase().trim();
    if (tagNameRegex.test(processedTagName)) {
        return 'div';
    }
    return processedTagName;
}
function getCssRulesString(s) {
    try {
        var rules = s.rules || s.cssRules;
        return rules ? Array.from(rules).map(getCssRuleString).join('') : null;
    }
    catch (error) {
        return null;
    }
}
function getCssRuleString(rule) {
    var cssStringified = rule.cssText;
    if (isCSSImportRule(rule)) {
        try {
            cssStringified = getCssRulesString(rule.styleSheet) || cssStringified;
        }
        catch (_a) {
        }
    }
    return cssStringified;
}
function isCSSImportRule(rule) {
    return 'styleSheet' in rule;
}
function stringifyStyleSheet(sheet) {
    return sheet.cssRules
        ? Array.from(sheet.cssRules)
            .map(function (rule) { return rule.cssText || ''; })
            .join('')
        : '';
}
function extractOrigin(url) {
    var origin = '';
    if (url.indexOf('//') > -1) {
        origin = url.split('/').slice(0, 3).join('/');
    }
    else {
        origin = url.split('/')[0];
    }
    origin = origin.split('?')[0];
    return origin;
}
var canvasService;
var canvasCtx;
var URL_IN_CSS_REF = /url\((?:(')([^']*)'|(")(.*?)"|([^)]*))\)/gm;
var RELATIVE_PATH = /^(?!www\.|(?:http|ftp)s?:\/\/|[A-Za-z]:\\|\/\/|#).*/;
var DATA_URI = /^(data:)([^,]*),(.*)/i;
function absoluteToStylesheet(cssText, href) {
    return (cssText || '').replace(URL_IN_CSS_REF, function (origin, quote1, path1, quote2, path2, path3) {
        var filePath = path1 || path2 || path3;
        var maybeQuote = quote1 || quote2 || '';
        if (!filePath) {
            return origin;
        }
        if (!RELATIVE_PATH.test(filePath)) {
            return "url(" + maybeQuote + filePath + maybeQuote + ")";
        }
        if (DATA_URI.test(filePath)) {
            return "url(" + maybeQuote + filePath + maybeQuote + ")";
        }
        if (filePath[0] === '/') {
            return "url(" + maybeQuote + (extractOrigin(href) + filePath) + maybeQuote + ")";
        }
        var stack = href.split('/');
        var parts = filePath.split('/');
        stack.pop();
        for (var _i = 0, parts_1 = parts; _i < parts_1.length; _i++) {
            var part = parts_1[_i];
            if (part === '.') {
                continue;
            }
            else if (part === '..') {
                stack.pop();
            }
            else {
                stack.push(part);
            }
        }
        return "url(" + maybeQuote + stack.join('/') + maybeQuote + ")";
    });
}
var SRCSET_NOT_SPACES = /^[^ \t\n\r\u000c]+/;
var SRCSET_COMMAS_OR_SPACES = /^[, \t\n\r\u000c]+/;
function getAbsoluteSrcsetString(doc, attributeValue) {
    if (attributeValue.trim() === '') {
        return attributeValue;
    }
    var pos = 0;
    function collectCharacters(regEx) {
        var chars;
        var match = regEx.exec(attributeValue.substring(pos));
        if (match) {
            chars = match[0];
            pos += chars.length;
            return chars;
        }
        return '';
    }
    var output = [];
    while (true) {
        collectCharacters(SRCSET_COMMAS_OR_SPACES);
        if (pos >= attributeValue.length) {
            break;
        }
        var url = collectCharacters(SRCSET_NOT_SPACES);
        if (url.slice(-1) === ',') {
            url = absoluteToDoc(doc, url.substring(0, url.length - 1));
            output.push(url);
        }
        else {
            var descriptorsStr = '';
            url = absoluteToDoc(doc, url);
            var inParens = false;
            while (true) {
                var c = attributeValue.charAt(pos);
                if (c === '') {
                    output.push((url + descriptorsStr).trim());
                    break;
                }
                else if (!inParens) {
                    if (c === ',') {
                        pos += 1;
                        output.push((url + descriptorsStr).trim());
                        break;
                    }
                    else if (c === '(') {
                        inParens = true;
                    }
                }
                else {
                    if (c === ')') {
                        inParens = false;
                    }
                }
                descriptorsStr += c;
                pos += 1;
            }
        }
    }
    return output.join(', ');
}
function absoluteToDoc(doc, attributeValue) {
    if (!attributeValue || attributeValue.trim() === '') {
        return attributeValue;
    }
    var a = doc.createElement('a');
    a.href = attributeValue;
    return a.href;
}
function isSVGElement(el) {
    return Boolean(el.tagName === 'svg' || el.ownerSVGElement);
}
function getHref() {
    var a = document.createElement('a');
    a.href = '';
    return a.href;
}
function transformAttribute(doc, tagName, name, value) {
    if (name === 'src' || (name === 'href' && value)) {
        return absoluteToDoc(doc, value);
    }
    else if (name === 'xlink:href' && value && value[0] !== '#') {
        return absoluteToDoc(doc, value);
    }
    else if (name === 'background' &&
        value &&
        (tagName === 'table' || tagName === 'td' || tagName === 'th')) {
        return absoluteToDoc(doc, value);
    }
    else if (name === 'srcset' && value) {
        return getAbsoluteSrcsetString(doc, value);
    }
    else if (name === 'style' && value) {
        return absoluteToStylesheet(value, getHref());
    }
    else if (tagName === 'object' && name === 'data' && value) {
        return absoluteToDoc(doc, value);
    }
    else {
        return value;
    }
}
function _isBlockedElement(element, blockClass, blockSelector) {
    if (typeof blockClass === 'string') {
        if (element.classList.contains(blockClass)) {
            return true;
        }
    }
    else {
        for (var eIndex = 0; eIndex < element.classList.length; eIndex++) {
            var className = element.classList[eIndex];
            if (blockClass.test(className)) {
                return true;
            }
        }
    }
    if (blockSelector) {
        return element.matches(blockSelector);
    }
    return false;
}
function needMaskingText(node, maskTextClass, maskTextSelector) {
    if (!node) {
        return false;
    }
    if (node.nodeType === node.ELEMENT_NODE) {
        if (typeof maskTextClass === 'string') {
            if (node.classList.contains(maskTextClass)) {
                return true;
            }
        }
        else {
            for (var eIndex = 0; eIndex < node.classList.length; eIndex++) {
                var className = node.classList[eIndex];
                if (maskTextClass.test(className)) {
                    return true;
                }
            }
        }
        if (maskTextSelector) {
            if (node.matches(maskTextSelector)) {
                return true;
            }
        }
        return needMaskingText(node.parentNode, maskTextClass, maskTextSelector);
    }
    if (node.nodeType === node.TEXT_NODE) {
        return needMaskingText(node.parentNode, maskTextClass, maskTextSelector);
    }
    return needMaskingText(node.parentNode, maskTextClass, maskTextSelector);
}
function onceIframeLoaded(iframeEl, listener, iframeLoadTimeout) {
    var win = iframeEl.contentWindow;
    if (!win) {
        return;
    }
    var fired = false;
    var readyState;
    try {
        readyState = win.document.readyState;
    }
    catch (error) {
        return;
    }
    if (readyState !== 'complete') {
        var timer_1 = setTimeout(function () {
            if (!fired) {
                listener();
                fired = true;
            }
        }, iframeLoadTimeout);
        iframeEl.addEventListener('load', function () {
            clearTimeout(timer_1);
            fired = true;
            listener();
        });
        return;
    }
    var blankUrl = 'about:blank';
    if (win.location.href !== blankUrl ||
        iframeEl.src === blankUrl ||
        iframeEl.src === '') {
        setTimeout(listener, 0);
        return;
    }
    iframeEl.addEventListener('load', listener);
}
function serializeNode(n, options) {
    var _a;
    var doc = options.doc, blockClass = options.blockClass, blockSelector = options.blockSelector, maskTextClass = options.maskTextClass, maskTextSelector = options.maskTextSelector, inlineStylesheet = options.inlineStylesheet, _b = options.maskInputOptions, maskInputOptions = _b === void 0 ? {} : _b, maskTextFn = options.maskTextFn, maskInputFn = options.maskInputFn, _c = options.dataURLOptions, dataURLOptions = _c === void 0 ? {} : _c, inlineImages = options.inlineImages, recordCanvas = options.recordCanvas, keepIframeSrcFn = options.keepIframeSrcFn;
    var rootId;
    if (doc.__sn) {
        var docId = doc.__sn.id;
        rootId = docId === 1 ? undefined : docId;
    }
    switch (n.nodeType) {
        case n.DOCUMENT_NODE:
            if (n.compatMode !== 'CSS1Compat') {
                return {
                    type: exports.NodeType.Document,
                    childNodes: [],
                    compatMode: n.compatMode,
                    rootId: rootId
                };
            }
            else {
                return {
                    type: exports.NodeType.Document,
                    childNodes: [],
                    rootId: rootId
                };
            }
        case n.DOCUMENT_TYPE_NODE:
            return {
                type: exports.NodeType.DocumentType,
                name: n.name,
                publicId: n.publicId,
                systemId: n.systemId,
                rootId: rootId
            };
        case n.ELEMENT_NODE:
            var needBlock = _isBlockedElement(n, blockClass, blockSelector);
            var tagName = getValidTagName(n);
            var attributes_1 = {};
            for (var _i = 0, _d = Array.from(n.attributes); _i < _d.length; _i++) {
                var _e = _d[_i], name_1 = _e.name, value = _e.value;
                attributes_1[name_1] = transformAttribute(doc, tagName, name_1, value);
            }
            if (tagName === 'link' && inlineStylesheet) {
                var stylesheet = Array.from(doc.styleSheets).find(function (s) {
                    return s.href === n.href;
                });
                var cssText = null;
                if (stylesheet) {
                    cssText = getCssRulesString(stylesheet);
                }
                if (cssText) {
                    delete attributes_1.rel;
                    delete attributes_1.href;
                    attributes_1._cssText = absoluteToStylesheet(cssText, stylesheet.href);
                }
            }
            if (tagName === 'style' &&
                n.sheet &&
                !(n.innerText ||
                    n.textContent ||
                    '').trim().length) {
                var cssText = getCssRulesString(n.sheet);
                if (cssText) {
                    attributes_1._cssText = absoluteToStylesheet(cssText, getHref());
                }
            }
            if (tagName === 'input' ||
                tagName === 'textarea' ||
                tagName === 'select') {
                var value = n.value;
                if (attributes_1.type !== 'radio' &&
                    attributes_1.type !== 'checkbox' &&
                    attributes_1.type !== 'submit' &&
                    attributes_1.type !== 'button' &&
                    value) {
                    attributes_1.value = maskInputValue({
                        type: attributes_1.type,
                        tagName: tagName,
                        value: value,
                        maskInputOptions: maskInputOptions,
                        maskInputFn: maskInputFn
                    });
                }
                else if (n.checked) {
                    attributes_1.checked = n.checked;
                }
            }
            if (tagName === 'option') {
                if (n.selected && !maskInputOptions['select']) {
                    attributes_1.selected = true;
                }
                else {
                    delete attributes_1.selected;
                }
            }
            if (tagName === 'canvas' && recordCanvas) {
                if (n.__context === '2d') {
                    if (!is2DCanvasBlank(n)) {
                        attributes_1.rr_dataURL = n.toDataURL(dataURLOptions.type, dataURLOptions.quality);
                    }
                }
                else if (!('__context' in n)) {
                    var canvasDataURL = n.toDataURL(dataURLOptions.type, dataURLOptions.quality);
                    var blankCanvas = document.createElement('canvas');
                    blankCanvas.width = n.width;
                    blankCanvas.height = n.height;
                    var blankCanvasDataURL = blankCanvas.toDataURL(dataURLOptions.type, dataURLOptions.quality);
                    if (canvasDataURL !== blankCanvasDataURL) {
                        attributes_1.rr_dataURL = canvasDataURL;
                    }
                }
            }
            if (tagName === 'img' && inlineImages) {
                if (!canvasService) {
                    canvasService = doc.createElement('canvas');
                    canvasCtx = canvasService.getContext('2d');
                }
                var image_1 = n;
                var oldValue_1 = image_1.crossOrigin;
                image_1.crossOrigin = 'anonymous';
                var recordInlineImage = function () {
                    try {
                        canvasService.width = image_1.naturalWidth;
                        canvasService.height = image_1.naturalHeight;
                        canvasCtx.drawImage(image_1, 0, 0);
                        attributes_1.rr_dataURL = canvasService.toDataURL(dataURLOptions.type, dataURLOptions.quality);
                    }
                    catch (err) {
                        console.warn("Cannot inline img src=" + image_1.currentSrc + "! Error: " + err);
                    }
                    oldValue_1
                        ? (attributes_1.crossOrigin = oldValue_1)
                        : delete attributes_1.crossOrigin;
                };
                if (image_1.complete && image_1.naturalWidth !== 0)
                    recordInlineImage();
                else
                    image_1.onload = recordInlineImage;
            }
            if (tagName === 'audio' || tagName === 'video') {
                attributes_1.rr_mediaState = n.paused
                    ? 'paused'
                    : 'played';
                attributes_1.rr_mediaCurrentTime = n.currentTime;
            }
            if (n.scrollLeft) {
                attributes_1.rr_scrollLeft = n.scrollLeft;
            }
            if (n.scrollTop) {
                attributes_1.rr_scrollTop = n.scrollTop;
            }
            if (needBlock) {
                var _f = n.getBoundingClientRect(), width = _f.width, height = _f.height;
                attributes_1 = {
                    "class": attributes_1["class"],
                    rr_width: width + "px",
                    rr_height: height + "px"
                };
            }
            if (tagName === 'iframe' && !keepIframeSrcFn(attributes_1.src)) {
                if (!n.contentDocument) {
                    attributes_1.rr_src = attributes_1.src;
                }
                delete attributes_1.src;
            }
            return {
                type: exports.NodeType.Element,
                tagName: tagName,
                attributes: attributes_1,
                childNodes: [],
                isSVG: isSVGElement(n) || undefined,
                needBlock: needBlock,
                rootId: rootId
            };
        case n.TEXT_NODE:
            var parentTagName = n.parentNode && n.parentNode.tagName;
            var textContent = n.textContent;
            var isStyle = parentTagName === 'STYLE' ? true : undefined;
            var isScript = parentTagName === 'SCRIPT' ? true : undefined;
            if (isStyle && textContent) {
                try {
                    if (n.nextSibling || n.previousSibling) {
                    }
                    else if ((_a = n.parentNode.sheet) === null || _a === void 0 ? void 0 : _a.cssRules) {
                        textContent = stringifyStyleSheet(n.parentNode.sheet);
                    }
                }
                catch (err) {
                    console.warn("Cannot get CSS styles from text's parentNode. Error: " + err, n);
                }
                textContent = absoluteToStylesheet(textContent, getHref());
            }
            if (isScript) {
                textContent = 'SCRIPT_PLACEHOLDER';
            }
            if (!isStyle &&
                !isScript &&
                needMaskingText(n, maskTextClass, maskTextSelector) &&
                textContent) {
                textContent = maskTextFn
                    ? maskTextFn(textContent)
                    : textContent.replace(/[\S]/g, '*');
            }
            return {
                type: exports.NodeType.Text,
                textContent: textContent || '',
                isStyle: isStyle,
                rootId: rootId
            };
        case n.CDATA_SECTION_NODE:
            return {
                type: exports.NodeType.CDATA,
                textContent: '',
                rootId: rootId
            };
        case n.COMMENT_NODE:
            return {
                type: exports.NodeType.Comment,
                textContent: n.textContent || '',
                rootId: rootId
            };
        default:
            return false;
    }
}
function lowerIfExists(maybeAttr) {
    if (maybeAttr === undefined) {
        return '';
    }
    else {
        return maybeAttr.toLowerCase();
    }
}
function slimDOMExcluded(sn, slimDOMOptions) {
    if (slimDOMOptions.comment && sn.type === exports.NodeType.Comment) {
        return true;
    }
    else if (sn.type === exports.NodeType.Element) {
        if (slimDOMOptions.script &&
            (sn.tagName === 'script' ||
                (sn.tagName === 'link' &&
                    sn.attributes.rel === 'preload' &&
                    sn.attributes.as === 'script') ||
                (sn.tagName === 'link' &&
                    sn.attributes.rel === 'prefetch' &&
                    typeof sn.attributes.href === 'string' &&
                    sn.attributes.href.endsWith('.js')))) {
            return true;
        }
        else if (slimDOMOptions.headFavicon &&
            ((sn.tagName === 'link' && sn.attributes.rel === 'shortcut icon') ||
                (sn.tagName === 'meta' &&
                    (lowerIfExists(sn.attributes.name).match(/^msapplication-tile(image|color)$/) ||
                        lowerIfExists(sn.attributes.name) === 'application-name' ||
                        lowerIfExists(sn.attributes.rel) === 'icon' ||
                        lowerIfExists(sn.attributes.rel) === 'apple-touch-icon' ||
                        lowerIfExists(sn.attributes.rel) === 'shortcut icon')))) {
            return true;
        }
        else if (sn.tagName === 'meta') {
            if (slimDOMOptions.headMetaDescKeywords &&
                lowerIfExists(sn.attributes.name).match(/^description|keywords$/)) {
                return true;
            }
            else if (slimDOMOptions.headMetaSocial &&
                (lowerIfExists(sn.attributes.property).match(/^(og|twitter|fb):/) ||
                    lowerIfExists(sn.attributes.name).match(/^(og|twitter):/) ||
                    lowerIfExists(sn.attributes.name) === 'pinterest')) {
                return true;
            }
            else if (slimDOMOptions.headMetaRobots &&
                (lowerIfExists(sn.attributes.name) === 'robots' ||
                    lowerIfExists(sn.attributes.name) === 'googlebot' ||
                    lowerIfExists(sn.attributes.name) === 'bingbot')) {
                return true;
            }
            else if (slimDOMOptions.headMetaHttpEquiv &&
                sn.attributes['http-equiv'] !== undefined) {
                return true;
            }
            else if (slimDOMOptions.headMetaAuthorship &&
                (lowerIfExists(sn.attributes.name) === 'author' ||
                    lowerIfExists(sn.attributes.name) === 'generator' ||
                    lowerIfExists(sn.attributes.name) === 'framework' ||
                    lowerIfExists(sn.attributes.name) === 'publisher' ||
                    lowerIfExists(sn.attributes.name) === 'progid' ||
                    lowerIfExists(sn.attributes.property).match(/^article:/) ||
                    lowerIfExists(sn.attributes.property).match(/^product:/))) {
                return true;
            }
            else if (slimDOMOptions.headMetaVerification &&
                (lowerIfExists(sn.attributes.name) === 'google-site-verification' ||
                    lowerIfExists(sn.attributes.name) === 'yandex-verification' ||
                    lowerIfExists(sn.attributes.name) === 'csrf-token' ||
                    lowerIfExists(sn.attributes.name) === 'p:domain_verify' ||
                    lowerIfExists(sn.attributes.name) === 'verify-v1' ||
                    lowerIfExists(sn.attributes.name) === 'verification' ||
                    lowerIfExists(sn.attributes.name) === 'shopify-checkout-api-token')) {
                return true;
            }
        }
    }
    return false;
}
function serializeNodeWithId(n, options) {
    var doc = options.doc, map = options.map, blockClass = options.blockClass, blockSelector = options.blockSelector, maskTextClass = options.maskTextClass, maskTextSelector = options.maskTextSelector, _a = options.skipChild, skipChild = _a === void 0 ? false : _a, _b = options.inlineStylesheet, inlineStylesheet = _b === void 0 ? true : _b, _c = options.maskInputOptions, maskInputOptions = _c === void 0 ? {} : _c, maskTextFn = options.maskTextFn, maskInputFn = options.maskInputFn, slimDOMOptions = options.slimDOMOptions, _d = options.dataURLOptions, dataURLOptions = _d === void 0 ? {} : _d, _e = options.inlineImages, inlineImages = _e === void 0 ? false : _e, _f = options.recordCanvas, recordCanvas = _f === void 0 ? false : _f, onSerialize = options.onSerialize, onIframeLoad = options.onIframeLoad, _g = options.iframeLoadTimeout, iframeLoadTimeout = _g === void 0 ? 5000 : _g, _h = options.keepIframeSrcFn, keepIframeSrcFn = _h === void 0 ? function () { return false; } : _h;
    var _j = options.preserveWhiteSpace, preserveWhiteSpace = _j === void 0 ? true : _j;
    var _serializedNode = serializeNode(n, {
        doc: doc,
        blockClass: blockClass,
        blockSelector: blockSelector,
        maskTextClass: maskTextClass,
        maskTextSelector: maskTextSelector,
        inlineStylesheet: inlineStylesheet,
        maskInputOptions: maskInputOptions,
        maskTextFn: maskTextFn,
        maskInputFn: maskInputFn,
        dataURLOptions: dataURLOptions,
        inlineImages: inlineImages,
        recordCanvas: recordCanvas,
        keepIframeSrcFn: keepIframeSrcFn
    });
    if (!_serializedNode) {
        console.warn(n, 'not serialized');
        return null;
    }
    var id;
    if ('__sn' in n) {
        id = n.__sn.id;
    }
    else if (slimDOMExcluded(_serializedNode, slimDOMOptions) ||
        (!preserveWhiteSpace &&
            _serializedNode.type === exports.NodeType.Text &&
            !_serializedNode.isStyle &&
            !_serializedNode.textContent.replace(/^\s+|\s+$/gm, '').length)) {
        id = IGNORED_NODE;
    }
    else {
        id = genId();
    }
    var serializedNode = Object.assign(_serializedNode, { id: id });
    n.__sn = serializedNode;
    if (id === IGNORED_NODE) {
        return null;
    }
    map[id] = n;
    if (onSerialize) {
        onSerialize(n);
    }
    var recordChild = !skipChild;
    if (serializedNode.type === exports.NodeType.Element) {
        recordChild = recordChild && !serializedNode.needBlock;
        delete serializedNode.needBlock;
        if (n.shadowRoot)
            serializedNode.isShadowHost = true;
    }
    if ((serializedNode.type === exports.NodeType.Document ||
        serializedNode.type === exports.NodeType.Element) &&
        recordChild) {
        if (slimDOMOptions.headWhitespace &&
            _serializedNode.type === exports.NodeType.Element &&
            _serializedNode.tagName === 'head') {
            preserveWhiteSpace = false;
        }
        var bypassOptions = {
            doc: doc,
            map: map,
            blockClass: blockClass,
            blockSelector: blockSelector,
            maskTextClass: maskTextClass,
            maskTextSelector: maskTextSelector,
            skipChild: skipChild,
            inlineStylesheet: inlineStylesheet,
            maskInputOptions: maskInputOptions,
            maskTextFn: maskTextFn,
            maskInputFn: maskInputFn,
            slimDOMOptions: slimDOMOptions,
            dataURLOptions: dataURLOptions,
            inlineImages: inlineImages,
            recordCanvas: recordCanvas,
            preserveWhiteSpace: preserveWhiteSpace,
            onSerialize: onSerialize,
            onIframeLoad: onIframeLoad,
            iframeLoadTimeout: iframeLoadTimeout,
            keepIframeSrcFn: keepIframeSrcFn
        };
        for (var _i = 0, _k = Array.from(n.childNodes); _i < _k.length; _i++) {
            var childN = _k[_i];
            var serializedChildNode = serializeNodeWithId(childN, bypassOptions);
            if (serializedChildNode) {
                serializedNode.childNodes.push(serializedChildNode);
            }
        }
        if (isElement(n) && n.shadowRoot) {
            for (var _l = 0, _m = Array.from(n.shadowRoot.childNodes); _l < _m.length; _l++) {
                var childN = _m[_l];
                var serializedChildNode = serializeNodeWithId(childN, bypassOptions);
                if (serializedChildNode) {
                    serializedChildNode.isShadow = true;
                    serializedNode.childNodes.push(serializedChildNode);
                }
            }
        }
    }
    if (n.parentNode && isShadowRoot(n.parentNode)) {
        serializedNode.isShadow = true;
    }
    if (serializedNode.type === exports.NodeType.Element &&
        serializedNode.tagName === 'iframe') {
        onceIframeLoaded(n, function () {
            var iframeDoc = n.contentDocument;
            if (iframeDoc && onIframeLoad) {
                var serializedIframeNode = serializeNodeWithId(iframeDoc, {
                    doc: iframeDoc,
                    map: map,
                    blockClass: blockClass,
                    blockSelector: blockSelector,
                    maskTextClass: maskTextClass,
                    maskTextSelector: maskTextSelector,
                    skipChild: false,
                    inlineStylesheet: inlineStylesheet,
                    maskInputOptions: maskInputOptions,
                    maskTextFn: maskTextFn,
                    maskInputFn: maskInputFn,
                    slimDOMOptions: slimDOMOptions,
                    dataURLOptions: dataURLOptions,
                    inlineImages: inlineImages,
                    recordCanvas: recordCanvas,
                    preserveWhiteSpace: preserveWhiteSpace,
                    onSerialize: onSerialize,
                    onIframeLoad: onIframeLoad,
                    iframeLoadTimeout: iframeLoadTimeout,
                    keepIframeSrcFn: keepIframeSrcFn
                });
                if (serializedIframeNode) {
                    onIframeLoad(n, serializedIframeNode);
                }
            }
        }, iframeLoadTimeout);
    }
    return serializedNode;
}
function snapshot(n, options) {
    var _a = options || {}, _b = _a.blockClass, blockClass = _b === void 0 ? 'rr-block' : _b, _c = _a.blockSelector, blockSelector = _c === void 0 ? null : _c, _d = _a.maskTextClass, maskTextClass = _d === void 0 ? 'rr-mask' : _d, _e = _a.maskTextSelector, maskTextSelector = _e === void 0 ? null : _e, _f = _a.inlineStylesheet, inlineStylesheet = _f === void 0 ? true : _f, _g = _a.inlineImages, inlineImages = _g === void 0 ? false : _g, _h = _a.recordCanvas, recordCanvas = _h === void 0 ? false : _h, _j = _a.maskAllInputs, maskAllInputs = _j === void 0 ? false : _j, maskTextFn = _a.maskTextFn, maskInputFn = _a.maskInputFn, _k = _a.slimDOM, slimDOM = _k === void 0 ? false : _k, dataURLOptions = _a.dataURLOptions, preserveWhiteSpace = _a.preserveWhiteSpace, onSerialize = _a.onSerialize, onIframeLoad = _a.onIframeLoad, iframeLoadTimeout = _a.iframeLoadTimeout, _l = _a.keepIframeSrcFn, keepIframeSrcFn = _l === void 0 ? function () { return false; } : _l;
    var idNodeMap = {};
    var maskInputOptions = maskAllInputs === true
        ? {
            color: true,
            date: true,
            'datetime-local': true,
            email: true,
            month: true,
            number: true,
            range: true,
            search: true,
            tel: true,
            text: true,
            time: true,
            url: true,
            week: true,
            textarea: true,
            select: true,
            password: true
        }
        : maskAllInputs === false
            ? {
                password: true
            }
            : maskAllInputs;
    var slimDOMOptions = slimDOM === true || slimDOM === 'all'
        ?
            {
                script: true,
                comment: true,
                headFavicon: true,
                headWhitespace: true,
                headMetaDescKeywords: slimDOM === 'all',
                headMetaSocial: true,
                headMetaRobots: true,
                headMetaHttpEquiv: true,
                headMetaAuthorship: true,
                headMetaVerification: true
            }
        : slimDOM === false
            ? {}
            : slimDOM;
    return [
        serializeNodeWithId(n, {
            doc: n,
            map: idNodeMap,
            blockClass: blockClass,
            blockSelector: blockSelector,
            maskTextClass: maskTextClass,
            maskTextSelector: maskTextSelector,
            skipChild: false,
            inlineStylesheet: inlineStylesheet,
            maskInputOptions: maskInputOptions,
            maskTextFn: maskTextFn,
            maskInputFn: maskInputFn,
            slimDOMOptions: slimDOMOptions,
            dataURLOptions: dataURLOptions,
            inlineImages: inlineImages,
            recordCanvas: recordCanvas,
            preserveWhiteSpace: preserveWhiteSpace,
            onSerialize: onSerialize,
            onIframeLoad: onIframeLoad,
            iframeLoadTimeout: iframeLoadTimeout,
            keepIframeSrcFn: keepIframeSrcFn
        }),
        idNodeMap,
    ];
}

var commentre = /\/\*[^*]*\*+([^/*][^*]*\*+)*\//g;
function parse(css, options) {
    if (options === void 0) { options = {}; }
    var lineno = 1;
    var column = 1;
    function updatePosition(str) {
        var lines = str.match(/\n/g);
        if (lines) {
            lineno += lines.length;
        }
        var i = str.lastIndexOf('\n');
        column = i === -1 ? column + str.length : str.length - i;
    }
    function position() {
        var start = { line: lineno, column: column };
        return function (node) {
            node.position = new Position(start);
            whitespace();
            return node;
        };
    }
    var Position = (function () {
        function Position(start) {
            this.start = start;
            this.end = { line: lineno, column: column };
            this.source = options.source;
        }
        return Position;
    }());
    Position.prototype.content = css;
    var errorsList = [];
    function error(msg) {
        var err = new Error(options.source + ':' + lineno + ':' + column + ': ' + msg);
        err.reason = msg;
        err.filename = options.source;
        err.line = lineno;
        err.column = column;
        err.source = css;
        if (options.silent) {
            errorsList.push(err);
        }
        else {
            throw err;
        }
    }
    function stylesheet() {
        var rulesList = rules();
        return {
            type: 'stylesheet',
            stylesheet: {
                source: options.source,
                rules: rulesList,
                parsingErrors: errorsList
            }
        };
    }
    function open() {
        return match(/^{\s*/);
    }
    function close() {
        return match(/^}/);
    }
    function rules() {
        var node;
        var rules = [];
        whitespace();
        comments(rules);
        while (css.length && css.charAt(0) !== '}' && (node = atrule() || rule())) {
            if (node !== false) {
                rules.push(node);
                comments(rules);
            }
        }
        return rules;
    }
    function match(re) {
        var m = re.exec(css);
        if (!m) {
            return;
        }
        var str = m[0];
        updatePosition(str);
        css = css.slice(str.length);
        return m;
    }
    function whitespace() {
        match(/^\s*/);
    }
    function comments(rules) {
        if (rules === void 0) { rules = []; }
        var c;
        while ((c = comment())) {
            if (c !== false) {
                rules.push(c);
            }
            c = comment();
        }
        return rules;
    }
    function comment() {
        var pos = position();
        if ('/' !== css.charAt(0) || '*' !== css.charAt(1)) {
            return;
        }
        var i = 2;
        while ('' !== css.charAt(i) &&
            ('*' !== css.charAt(i) || '/' !== css.charAt(i + 1))) {
            ++i;
        }
        i += 2;
        if ('' === css.charAt(i - 1)) {
            return error('End of comment missing');
        }
        var str = css.slice(2, i - 2);
        column += 2;
        updatePosition(str);
        css = css.slice(i);
        column += 2;
        return pos({
            type: 'comment',
            comment: str
        });
    }
    function selector() {
        var m = match(/^([^{]+)/);
        if (!m) {
            return;
        }
        return trim(m[0])
            .replace(/\/\*([^*]|[\r\n]|(\*+([^*/]|[\r\n])))*\*\/+/g, '')
            .replace(/"(?:\\"|[^"])*"|'(?:\\'|[^'])*'/g, function (m) {
            return m.replace(/,/g, '\u200C');
        })
            .split(/\s*(?![^(]*\)),\s*/)
            .map(function (s) {
            return s.replace(/\u200C/g, ',');
        });
    }
    function declaration() {
        var pos = position();
        var propMatch = match(/^(\*?[-#\/\*\\\w]+(\[[0-9a-z_-]+\])?)\s*/);
        if (!propMatch) {
            return;
        }
        var prop = trim(propMatch[0]);
        if (!match(/^:\s*/)) {
            return error("property missing ':'");
        }
        var val = match(/^((?:'(?:\\'|.)*?'|"(?:\\"|.)*?"|\([^\)]*?\)|[^};])+)/);
        var ret = pos({
            type: 'declaration',
            property: prop.replace(commentre, ''),
            value: val ? trim(val[0]).replace(commentre, '') : ''
        });
        match(/^[;\s]*/);
        return ret;
    }
    function declarations() {
        var decls = [];
        if (!open()) {
            return error("missing '{'");
        }
        comments(decls);
        var decl;
        while ((decl = declaration())) {
            if (decl !== false) {
                decls.push(decl);
                comments(decls);
            }
            decl = declaration();
        }
        if (!close()) {
            return error("missing '}'");
        }
        return decls;
    }
    function keyframe() {
        var m;
        var vals = [];
        var pos = position();
        while ((m = match(/^((\d+\.\d+|\.\d+|\d+)%?|[a-z]+)\s*/))) {
            vals.push(m[1]);
            match(/^,\s*/);
        }
        if (!vals.length) {
            return;
        }
        return pos({
            type: 'keyframe',
            values: vals,
            declarations: declarations()
        });
    }
    function atkeyframes() {
        var pos = position();
        var m = match(/^@([-\w]+)?keyframes\s*/);
        if (!m) {
            return;
        }
        var vendor = m[1];
        m = match(/^([-\w]+)\s*/);
        if (!m) {
            return error('@keyframes missing name');
        }
        var name = m[1];
        if (!open()) {
            return error("@keyframes missing '{'");
        }
        var frame;
        var frames = comments();
        while ((frame = keyframe())) {
            frames.push(frame);
            frames = frames.concat(comments());
        }
        if (!close()) {
            return error("@keyframes missing '}'");
        }
        return pos({
            type: 'keyframes',
            name: name,
            vendor: vendor,
            keyframes: frames
        });
    }
    function atsupports() {
        var pos = position();
        var m = match(/^@supports *([^{]+)/);
        if (!m) {
            return;
        }
        var supports = trim(m[1]);
        if (!open()) {
            return error("@supports missing '{'");
        }
        var style = comments().concat(rules());
        if (!close()) {
            return error("@supports missing '}'");
        }
        return pos({
            type: 'supports',
            supports: supports,
            rules: style
        });
    }
    function athost() {
        var pos = position();
        var m = match(/^@host\s*/);
        if (!m) {
            return;
        }
        if (!open()) {
            return error("@host missing '{'");
        }
        var style = comments().concat(rules());
        if (!close()) {
            return error("@host missing '}'");
        }
        return pos({
            type: 'host',
            rules: style
        });
    }
    function atmedia() {
        var pos = position();
        var m = match(/^@media *([^{]+)/);
        if (!m) {
            return;
        }
        var media = trim(m[1]);
        if (!open()) {
            return error("@media missing '{'");
        }
        var style = comments().concat(rules());
        if (!close()) {
            return error("@media missing '}'");
        }
        return pos({
            type: 'media',
            media: media,
            rules: style
        });
    }
    function atcustommedia() {
        var pos = position();
        var m = match(/^@custom-media\s+(--[^\s]+)\s*([^{;]+);/);
        if (!m) {
            return;
        }
        return pos({
            type: 'custom-media',
            name: trim(m[1]),
            media: trim(m[2])
        });
    }
    function atpage() {
        var pos = position();
        var m = match(/^@page */);
        if (!m) {
            return;
        }
        var sel = selector() || [];
        if (!open()) {
            return error("@page missing '{'");
        }
        var decls = comments();
        var decl;
        while ((decl = declaration())) {
            decls.push(decl);
            decls = decls.concat(comments());
        }
        if (!close()) {
            return error("@page missing '}'");
        }
        return pos({
            type: 'page',
            selectors: sel,
            declarations: decls
        });
    }
    function atdocument() {
        var pos = position();
        var m = match(/^@([-\w]+)?document *([^{]+)/);
        if (!m) {
            return;
        }
        var vendor = trim(m[1]);
        var doc = trim(m[2]);
        if (!open()) {
            return error("@document missing '{'");
        }
        var style = comments().concat(rules());
        if (!close()) {
            return error("@document missing '}'");
        }
        return pos({
            type: 'document',
            document: doc,
            vendor: vendor,
            rules: style
        });
    }
    function atfontface() {
        var pos = position();
        var m = match(/^@font-face\s*/);
        if (!m) {
            return;
        }
        if (!open()) {
            return error("@font-face missing '{'");
        }
        var decls = comments();
        var decl;
        while ((decl = declaration())) {
            decls.push(decl);
            decls = decls.concat(comments());
        }
        if (!close()) {
            return error("@font-face missing '}'");
        }
        return pos({
            type: 'font-face',
            declarations: decls
        });
    }
    var atimport = _compileAtrule('import');
    var atcharset = _compileAtrule('charset');
    var atnamespace = _compileAtrule('namespace');
    function _compileAtrule(name) {
        var re = new RegExp('^@' + name + '\\s*([^;]+);');
        return function () {
            var pos = position();
            var m = match(re);
            if (!m) {
                return;
            }
            var ret = { type: name };
            ret[name] = m[1].trim();
            return pos(ret);
        };
    }
    function atrule() {
        if (css[0] !== '@') {
            return;
        }
        return (atkeyframes() ||
            atmedia() ||
            atcustommedia() ||
            atsupports() ||
            atimport() ||
            atcharset() ||
            atnamespace() ||
            atdocument() ||
            atpage() ||
            athost() ||
            atfontface());
    }
    function rule() {
        var pos = position();
        var sel = selector();
        if (!sel) {
            return error('selector missing');
        }
        comments();
        return pos({
            type: 'rule',
            selectors: sel,
            declarations: declarations()
        });
    }
    return addParent(stylesheet());
}
function trim(str) {
    return str ? str.replace(/^\s+|\s+$/g, '') : '';
}
function addParent(obj, parent) {
    var isNode = obj && typeof obj.type === 'string';
    var childParent = isNode ? obj : parent;
    for (var _i = 0, _a = Object.keys(obj); _i < _a.length; _i++) {
        var k = _a[_i];
        var value = obj[k];
        if (Array.isArray(value)) {
            value.forEach(function (v) {
                addParent(v, childParent);
            });
        }
        else if (value && typeof value === 'object') {
            addParent(value, childParent);
        }
    }
    if (isNode) {
        Object.defineProperty(obj, 'parent', {
            configurable: true,
            writable: true,
            enumerable: false,
            value: parent || null
        });
    }
    return obj;
}

var tagMap = {
    script: 'noscript',
    altglyph: 'altGlyph',
    altglyphdef: 'altGlyphDef',
    altglyphitem: 'altGlyphItem',
    animatecolor: 'animateColor',
    animatemotion: 'animateMotion',
    animatetransform: 'animateTransform',
    clippath: 'clipPath',
    feblend: 'feBlend',
    fecolormatrix: 'feColorMatrix',
    fecomponenttransfer: 'feComponentTransfer',
    fecomposite: 'feComposite',
    feconvolvematrix: 'feConvolveMatrix',
    fediffuselighting: 'feDiffuseLighting',
    fedisplacementmap: 'feDisplacementMap',
    fedistantlight: 'feDistantLight',
    fedropshadow: 'feDropShadow',
    feflood: 'feFlood',
    fefunca: 'feFuncA',
    fefuncb: 'feFuncB',
    fefuncg: 'feFuncG',
    fefuncr: 'feFuncR',
    fegaussianblur: 'feGaussianBlur',
    feimage: 'feImage',
    femerge: 'feMerge',
    femergenode: 'feMergeNode',
    femorphology: 'feMorphology',
    feoffset: 'feOffset',
    fepointlight: 'fePointLight',
    fespecularlighting: 'feSpecularLighting',
    fespotlight: 'feSpotLight',
    fetile: 'feTile',
    feturbulence: 'feTurbulence',
    foreignobject: 'foreignObject',
    glyphref: 'glyphRef',
    lineargradient: 'linearGradient',
    radialgradient: 'radialGradient'
};
function getTagName(n) {
    var tagName = tagMap[n.tagName] ? tagMap[n.tagName] : n.tagName;
    if (tagName === 'link' && n.attributes._cssText) {
        tagName = 'style';
    }
    return tagName;
}
function escapeRegExp(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
var HOVER_SELECTOR = /([^\\]):hover/;
var HOVER_SELECTOR_GLOBAL = new RegExp(HOVER_SELECTOR.source, 'g');
function addHoverClass(cssText, cache) {
    var cachedStyle = cache === null || cache === void 0 ? void 0 : cache.stylesWithHoverClass.get(cssText);
    if (cachedStyle)
        return cachedStyle;
    var ast = parse(cssText, {
        silent: true
    });
    if (!ast.stylesheet) {
        return cssText;
    }
    var selectors = [];
    ast.stylesheet.rules.forEach(function (rule) {
        if ('selectors' in rule) {
            (rule.selectors || []).forEach(function (selector) {
                if (HOVER_SELECTOR.test(selector)) {
                    selectors.push(selector);
                }
            });
        }
    });
    if (selectors.length === 0) {
        return cssText;
    }
    var selectorMatcher = new RegExp(selectors
        .filter(function (selector, index) { return selectors.indexOf(selector) === index; })
        .sort(function (a, b) { return b.length - a.length; })
        .map(function (selector) {
        return escapeRegExp(selector);
    })
        .join('|'), 'g');
    var result = cssText.replace(selectorMatcher, function (selector) {
        var newSelector = selector.replace(HOVER_SELECTOR_GLOBAL, '$1.\\:hover');
        return selector + ", " + newSelector;
    });
    cache === null || cache === void 0 ? void 0 : cache.stylesWithHoverClass.set(cssText, result);
    return result;
}
function createCache() {
    var stylesWithHoverClass = new Map();
    return {
        stylesWithHoverClass: stylesWithHoverClass
    };
}
function buildNode(n, options) {
    var doc = options.doc, hackCss = options.hackCss, cache = options.cache;
    switch (n.type) {
        case exports.NodeType.Document:
            return doc.implementation.createDocument(null, '', null);
        case exports.NodeType.DocumentType:
            return doc.implementation.createDocumentType(n.name || 'html', n.publicId, n.systemId);
        case exports.NodeType.Element:
            var tagName = getTagName(n);
            var node_1;
            if (n.isSVG) {
                node_1 = doc.createElementNS('http://www.w3.org/2000/svg', tagName);
            }
            else {
                node_1 = doc.createElement(tagName);
            }
            var _loop_1 = function (name_1) {
                if (!n.attributes.hasOwnProperty(name_1)) {
                    return "continue";
                }
                var value = n.attributes[name_1];
                if (tagName === 'option' && name_1 === 'selected' && value === false) {
                    return "continue";
                }
                value =
                    typeof value === 'boolean' || typeof value === 'number' ? '' : value;
                if (!name_1.startsWith('rr_')) {
                    var isTextarea = tagName === 'textarea' && name_1 === 'value';
                    var isRemoteOrDynamicCss = tagName === 'style' && name_1 === '_cssText';
                    if (isRemoteOrDynamicCss && hackCss) {
                        value = addHoverClass(value, cache);
                    }
                    if (isTextarea || isRemoteOrDynamicCss) {
                        var child = doc.createTextNode(value);
                        for (var _i = 0, _a = Array.from(node_1.childNodes); _i < _a.length; _i++) {
                            var c = _a[_i];
                            if (c.nodeType === node_1.TEXT_NODE) {
                                node_1.removeChild(c);
                            }
                        }
                        node_1.appendChild(child);
                        return "continue";
                    }
                    try {
                        if (n.isSVG && name_1 === 'xlink:href') {
                            node_1.setAttributeNS('http://www.w3.org/1999/xlink', name_1, value);
                        }
                        else if (name_1 === 'onload' ||
                            name_1 === 'onclick' ||
                            name_1.substring(0, 7) === 'onmouse') {
                            node_1.setAttribute('_' + name_1, value);
                        }
                        else if (tagName === 'meta' &&
                            n.attributes['http-equiv'] === 'Content-Security-Policy' &&
                            name_1 === 'content') {
                            node_1.setAttribute('csp-content', value);
                            return "continue";
                        }
                        else if (tagName === 'link' &&
                            n.attributes.rel === 'preload' &&
                            n.attributes.as === 'script') {
                        }
                        else if (tagName === 'link' &&
                            n.attributes.rel === 'prefetch' &&
                            typeof n.attributes.href === 'string' &&
                            n.attributes.href.endsWith('.js')) {
                        }
                        else if (tagName === 'img' &&
                            n.attributes.srcset &&
                            n.attributes.rr_dataURL) {
                            node_1.setAttribute('rrweb-original-srcset', n.attributes.srcset);
                        }
                        else {
                            node_1.setAttribute(name_1, value);
                        }
                    }
                    catch (error) {
                    }
                }
                else {
                    if (tagName === 'canvas' && name_1 === 'rr_dataURL') {
                        var image_1 = document.createElement('img');
                        image_1.src = value;
                        image_1.onload = function () {
                            var ctx = node_1.getContext('2d');
                            if (ctx) {
                                ctx.drawImage(image_1, 0, 0, image_1.width, image_1.height);
                            }
                        };
                    }
                    else if (tagName === 'img' && name_1 === 'rr_dataURL') {
                        var image = node_1;
                        if (!image.currentSrc.startsWith('data:')) {
                            image.setAttribute('rrweb-original-src', n.attributes.src);
                            image.src = value;
                        }
                    }
                    if (name_1 === 'rr_width') {
                        node_1.style.width = value;
                    }
                    else if (name_1 === 'rr_height') {
                        node_1.style.height = value;
                    }
                    else if (name_1 === 'rr_mediaCurrentTime') {
                        node_1.currentTime = n.attributes
                            .rr_mediaCurrentTime;
                    }
                    else if (name_1 === 'rr_mediaState') {
                        switch (value) {
                            case 'played':
                                node_1
                                    .play()["catch"](function (e) { return console.warn('media playback error', e); });
                                break;
                            case 'paused':
                                node_1.pause();
                                break;
                        }
                    }
                }
            };
            for (var name_1 in n.attributes) {
                _loop_1(name_1);
            }
            if (n.isShadowHost) {
                if (!node_1.shadowRoot) {
                    node_1.attachShadow({ mode: 'open' });
                }
                else {
                    while (node_1.shadowRoot.firstChild) {
                        node_1.shadowRoot.removeChild(node_1.shadowRoot.firstChild);
                    }
                }
            }
            return node_1;
        case exports.NodeType.Text:
            return doc.createTextNode(n.isStyle && hackCss
                ? addHoverClass(n.textContent, cache)
                : n.textContent);
        case exports.NodeType.CDATA:
            return doc.createCDATASection(n.textContent);
        case exports.NodeType.Comment:
            return doc.createComment(n.textContent);
        default:
            return null;
    }
}
function buildNodeWithSN(n, options) {
    var doc = options.doc, map = options.map, _a = options.skipChild, skipChild = _a === void 0 ? false : _a, _b = options.hackCss, hackCss = _b === void 0 ? true : _b, afterAppend = options.afterAppend, cache = options.cache;
    var node = buildNode(n, { doc: doc, hackCss: hackCss, cache: cache });
    if (!node) {
        return null;
    }
    if (n.rootId) {
        console.assert(map[n.rootId] === doc, 'Target document should has the same root id.');
    }
    if (n.type === exports.NodeType.Document) {
        doc.close();
        doc.open();
        if (n.compatMode === 'BackCompat' &&
            n.childNodes &&
            n.childNodes[0].type !== exports.NodeType.DocumentType) {
            if (n.childNodes[0].type === exports.NodeType.Element &&
                'xmlns' in n.childNodes[0].attributes &&
                n.childNodes[0].attributes.xmlns === 'http://www.w3.org/1999/xhtml') {
                doc.write('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "">');
            }
            else {
                doc.write('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN" "">');
            }
        }
        node = doc;
    }
    node.__sn = n;
    map[n.id] = node;
    if ((n.type === exports.NodeType.Document || n.type === exports.NodeType.Element) &&
        !skipChild) {
        for (var _i = 0, _c = n.childNodes; _i < _c.length; _i++) {
            var childN = _c[_i];
            var childNode = buildNodeWithSN(childN, {
                doc: doc,
                map: map,
                skipChild: false,
                hackCss: hackCss,
                afterAppend: afterAppend,
                cache: cache
            });
            if (!childNode) {
                console.warn('Failed to rebuild', childN);
                continue;
            }
            if (childN.isShadow && isElement(node) && node.shadowRoot) {
                node.shadowRoot.appendChild(childNode);
            }
            else {
                node.appendChild(childNode);
            }
            if (afterAppend) {
                afterAppend(childNode);
            }
        }
    }
    return node;
}
function visit(idNodeMap, onVisit) {
    function walk(node) {
        onVisit(node);
    }
    for (var key in idNodeMap) {
        if (idNodeMap[key]) {
            walk(idNodeMap[key]);
        }
    }
}
function handleScroll(node) {
    var n = node.__sn;
    if (n.type !== exports.NodeType.Element) {
        return;
    }
    var el = node;
    for (var name_2 in n.attributes) {
        if (!(n.attributes.hasOwnProperty(name_2) && name_2.startsWith('rr_'))) {
            continue;
        }
        var value = n.attributes[name_2];
        if (name_2 === 'rr_scrollLeft') {
            el.scrollLeft = value;
        }
        if (name_2 === 'rr_scrollTop') {
            el.scrollTop = value;
        }
    }
}
function rebuild(n, options) {
    var doc = options.doc, onVisit = options.onVisit, _a = options.hackCss, hackCss = _a === void 0 ? true : _a, afterAppend = options.afterAppend, cache = options.cache;
    var idNodeMap = {};
    var node = buildNodeWithSN(n, {
        doc: doc,
        map: idNodeMap,
        skipChild: false,
        hackCss: hackCss,
        afterAppend: afterAppend,
        cache: cache
    });
    visit(idNodeMap, function (visitedNode) {
        if (onVisit) {
            onVisit(visitedNode);
        }
        handleScroll(visitedNode);
    });
    return [node, idNodeMap];
}

exports.IGNORED_NODE = IGNORED_NODE;
exports.addHoverClass = addHoverClass;
exports.buildNodeWithSN = buildNodeWithSN;
exports.createCache = createCache;
exports.is2DCanvasBlank = is2DCanvasBlank;
exports.isElement = isElement;
exports.isShadowRoot = isShadowRoot;
exports.maskInputValue = maskInputValue;
exports.needMaskingText = needMaskingText;
exports.rebuild = rebuild;
exports.serializeNodeWithId = serializeNodeWithId;
exports.snapshot = snapshot;
exports.transformAttribute = transformAttribute;


},{}],55:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/*! *****************************************************************************
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
***************************************************************************** */

exports.__assign = function() {
    exports.__assign = Object.assign || function __assign(t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
        }
        return t;
    };
    return exports.__assign.apply(this, arguments);
};

function __rest(s, e) {
    var t = {};
    for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
        t[p] = s[p];
    if (s != null && typeof Object.getOwnPropertySymbols === "function")
        for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
            if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
                t[p[i]] = s[p[i]];
        }
    return t;
}

function __values(o) {
    var s = typeof Symbol === "function" && Symbol.iterator, m = s && o[s], i = 0;
    if (m) return m.call(o);
    if (o && typeof o.length === "number") return {
        next: function () {
            if (o && i >= o.length) o = void 0;
            return { value: o && o[i++], done: !o };
        }
    };
    throw new TypeError(s ? "Object is not iterable." : "Symbol.iterator is not defined.");
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

function __spreadArray(to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
            if (!ar) ar = Array.prototype.slice.call(from, 0, i);
            ar[i] = from[i];
        }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
}

exports.__read = __read;
exports.__rest = __rest;
exports.__spreadArray = __spreadArray;
exports.__values = __values;


},{}],56:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const index = require('../index.js');
const pack = require('../packer/pack.js');
const unpack = require('../packer/unpack.js');
const index$1 = require('../plugins/console/record/index.js');
const index$2 = require('../plugins/console/replay/index.js');
const index$3 = require('../record/index.js');
const types = require('../types.js');
const index$4 = require('../replay/index.js');
const utils = require('../utils.js');



exports.addCustomEvent = index.addCustomEvent;
exports.freezePage = index.freezePage;
exports.pack = pack.pack;
exports.unpack = unpack.unpack;
exports.PLUGIN_NAME = index$1.PLUGIN_NAME;
exports.getRecordConsolePlugin = index$1.getRecordConsolePlugin;
exports.getReplayConsolePlugin = index$2.getReplayConsolePlugin;
exports.record = index$3.default;
Object.defineProperty(exports, 'EventType', {
	enumerable: true,
	get: () => types.EventType
});
Object.defineProperty(exports, 'IncrementalSource', {
	enumerable: true,
	get: () => types.IncrementalSource
});
Object.defineProperty(exports, 'MouseInteractions', {
	enumerable: true,
	get: () => types.MouseInteractions
});
Object.defineProperty(exports, 'ReplayerEvents', {
	enumerable: true,
	get: () => types.ReplayerEvents
});
exports.Replayer = index$4.Replayer;
Object.defineProperty(exports, 'mirror', {
	enumerable: true,
	get: () => utils._mirror
});
exports.utils = utils;


},{"../index.js":57,"../packer/pack.js":59,"../packer/unpack.js":60,"../plugins/console/record/index.js":62,"../plugins/console/replay/index.js":64,"../record/index.js":66,"../replay/index.js":78,"../types.js":84,"../utils.js":85}],57:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const index = require('./record/index.js');
const index$1 = require('./replay/index.js');
const utils = require('./utils.js');
const types = require('./types.js');

var addCustomEvent = index.default.addCustomEvent;
var freezePage = index.default.freezePage;

exports.record = index.default;
exports.Replayer = index$1.Replayer;
Object.defineProperty(exports, 'mirror', {
	enumerable: true,
	get: () => utils._mirror
});
exports.utils = utils;
Object.defineProperty(exports, 'EventType', {
	enumerable: true,
	get: () => types.EventType
});
Object.defineProperty(exports, 'IncrementalSource', {
	enumerable: true,
	get: () => types.IncrementalSource
});
Object.defineProperty(exports, 'MouseInteractions', {
	enumerable: true,
	get: () => types.MouseInteractions
});
Object.defineProperty(exports, 'ReplayerEvents', {
	enumerable: true,
	get: () => types.ReplayerEvents
});
exports.addCustomEvent = addCustomEvent;
exports.freezePage = freezePage;


},{"./record/index.js":66,"./replay/index.js":78,"./types.js":84,"./utils.js":85}],58:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

var MARK = 'v1';

exports.MARK = MARK;


},{}],59:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');
const browser = require('../../../../ext/fflate/esm/browser.js');
const base = require('./base.js');

var pack = function (event) {
    var _e = tslib_es6.__assign(tslib_es6.__assign({}, event), { v: base.MARK });
    return browser.strFromU8(browser.zlibSync(browser.strToU8(JSON.stringify(_e))), true);
};

exports.pack = pack;


},{"../../../../ext/fflate/esm/browser.js":52,"../../ext/tslib/tslib.es6.js":55,"./base.js":58}],60:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const browser = require('../../../../ext/fflate/esm/browser.js');
const base = require('./base.js');

var unpack = function (raw) {
    if (typeof raw !== 'string') {
        return raw;
    }
    try {
        var e = JSON.parse(raw);
        if (e.timestamp) {
            return e;
        }
    }
    catch (error) {
    }
    try {
        var e = JSON.parse(browser.strFromU8(browser.unzlibSync(browser.strToU8(raw, true))));
        if (e.v === base.MARK) {
            return e;
        }
        throw new Error("These events were packed with packer ".concat(e.v, " which is incompatible with current packer ").concat(base.MARK, "."));
    }
    catch (error) {
        console.error(error);
        throw new Error('Unknown data format.');
    }
};

exports.unpack = unpack;


},{"../../../../ext/fflate/esm/browser.js":52,"./base.js":58}],61:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

var StackFrame = (function () {
    function StackFrame(obj) {
        this.fileName = obj.fileName || '';
        this.functionName = obj.functionName || '';
        this.lineNumber = obj.lineNumber;
        this.columnNumber = obj.columnNumber;
    }
    StackFrame.prototype.toString = function () {
        var lineNumber = this.lineNumber || '';
        var columnNumber = this.columnNumber || '';
        if (this.functionName) {
            return (this.functionName +
                ' (' +
                this.fileName +
                ':' +
                lineNumber +
                ':' +
                columnNumber +
                ')');
        }
        return this.fileName + ':' + lineNumber + ':' + columnNumber;
    };
    return StackFrame;
}());
var FIREFOX_SAFARI_STACK_REGEXP = /(^|@)\S+:\d+/;
var CHROME_IE_STACK_REGEXP = /^\s*at .*(\S+:\d+|\(native\))/m;
var SAFARI_NATIVE_CODE_REGEXP = /^(eval@)?(\[native code])?$/;
var ErrorStackParser = {
    parse: function (error) {
        if (!error) {
            return [];
        }
        if (typeof error.stacktrace !== 'undefined' ||
            typeof error['opera#sourceloc'] !== 'undefined') {
            return this.parseOpera(error);
        }
        else if (error.stack && error.stack.match(CHROME_IE_STACK_REGEXP)) {
            return this.parseV8OrIE(error);
        }
        else if (error.stack) {
            return this.parseFFOrSafari(error);
        }
        else {
            throw new Error('Cannot parse given Error object');
        }
    },
    extractLocation: function (urlLike) {
        if (urlLike.indexOf(':') === -1) {
            return [urlLike];
        }
        var regExp = /(.+?)(?::(\d+))?(?::(\d+))?$/;
        var parts = regExp.exec(urlLike.replace(/[()]/g, ''));
        if (!parts)
            throw new Error("Cannot parse given url: ".concat(urlLike));
        return [parts[1], parts[2] || undefined, parts[3] || undefined];
    },
    parseV8OrIE: function (error) {
        var filtered = error.stack.split('\n').filter(function (line) {
            return !!line.match(CHROME_IE_STACK_REGEXP);
        }, this);
        return filtered.map(function (line) {
            if (line.indexOf('(eval ') > -1) {
                line = line
                    .replace(/eval code/g, 'eval')
                    .replace(/(\(eval at [^()]*)|(\),.*$)/g, '');
            }
            var sanitizedLine = line.replace(/^\s+/, '').replace(/\(eval code/g, '(');
            var location = sanitizedLine.match(/ (\((.+):(\d+):(\d+)\)$)/);
            sanitizedLine = location
                ? sanitizedLine.replace(location[0], '')
                : sanitizedLine;
            var tokens = sanitizedLine.split(/\s+/).slice(1);
            var locationParts = this.extractLocation(location ? location[1] : tokens.pop());
            var functionName = tokens.join(' ') || undefined;
            var fileName = ['eval', '<anonymous>'].indexOf(locationParts[0]) > -1
                ? undefined
                : locationParts[0];
            return new StackFrame({
                functionName: functionName,
                fileName: fileName,
                lineNumber: locationParts[1],
                columnNumber: locationParts[2],
            });
        }, this);
    },
    parseFFOrSafari: function (error) {
        var filtered = error.stack.split('\n').filter(function (line) {
            return !line.match(SAFARI_NATIVE_CODE_REGEXP);
        }, this);
        return filtered.map(function (line) {
            if (line.indexOf(' > eval') > -1) {
                line = line.replace(/ line (\d+)(?: > eval line \d+)* > eval:\d+:\d+/g, ':$1');
            }
            if (line.indexOf('@') === -1 && line.indexOf(':') === -1) {
                return new StackFrame({
                    functionName: line,
                });
            }
            else {
                var functionNameRegex = /((.*".+"[^@]*)?[^@]*)(?:@)/;
                var matches = line.match(functionNameRegex);
                var functionName = matches && matches[1] ? matches[1] : undefined;
                var locationParts = this.extractLocation(line.replace(functionNameRegex, ''));
                return new StackFrame({
                    functionName: functionName,
                    fileName: locationParts[0],
                    lineNumber: locationParts[1],
                    columnNumber: locationParts[2],
                });
            }
        }, this);
    },
    parseOpera: function (e) {
        if (!e.stacktrace ||
            (e.message.indexOf('\n') > -1 &&
                e.message.split('\n').length > e.stacktrace.split('\n').length)) {
            return this.parseOpera9(e);
        }
        else if (!e.stack) {
            return this.parseOpera10(e);
        }
        else {
            return this.parseOpera11(e);
        }
    },
    parseOpera9: function (e) {
        var lineRE = /Line (\d+).*script (?:in )?(\S+)/i;
        var lines = e.message.split('\n');
        var result = [];
        for (var i = 2, len = lines.length; i < len; i += 2) {
            var match = lineRE.exec(lines[i]);
            if (match) {
                result.push(new StackFrame({
                    fileName: match[2],
                    lineNumber: parseFloat(match[1]),
                }));
            }
        }
        return result;
    },
    parseOpera10: function (e) {
        var lineRE = /Line (\d+).*script (?:in )?(\S+)(?:: In function (\S+))?$/i;
        var lines = e.stacktrace.split('\n');
        var result = [];
        for (var i = 0, len = lines.length; i < len; i += 2) {
            var match = lineRE.exec(lines[i]);
            if (match) {
                result.push(new StackFrame({
                    functionName: match[3] || undefined,
                    fileName: match[2],
                    lineNumber: parseFloat(match[1]),
                }));
            }
        }
        return result;
    },
    parseOpera11: function (error) {
        var filtered = error.stack.split('\n').filter(function (line) {
            return (!!line.match(FIREFOX_SAFARI_STACK_REGEXP) &&
                !line.match(/^Error created at/));
        }, this);
        return filtered.map(function (line) {
            var tokens = line.split('@');
            var locationParts = this.extractLocation(tokens.pop());
            var functionCall = tokens.shift() || '';
            var functionName = functionCall
                .replace(/<anonymous function(: (\w+))?>/, '$2')
                .replace(/\([^)]*\)/g, '') || undefined;
            return new StackFrame({
                functionName: functionName,
                fileName: locationParts[0],
                lineNumber: locationParts[1],
                columnNumber: locationParts[2],
            });
        }, this);
    },
};

exports.ErrorStackParser = ErrorStackParser;
exports.StackFrame = StackFrame;


},{}],62:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');
const utils = require('../../../utils.js');
const errorStackParser = require('./error-stack-parser.js');
const stringify = require('./stringify.js');

var defaultLogOptions = {
    level: [
        'assert',
        'clear',
        'count',
        'countReset',
        'debug',
        'dir',
        'dirxml',
        'error',
        'group',
        'groupCollapsed',
        'groupEnd',
        'info',
        'log',
        'table',
        'time',
        'timeEnd',
        'timeLog',
        'trace',
        'warn',
    ],
    lengthThreshold: 1000,
    logger: 'console',
};
function initLogObserver(cb, win, logOptions) {
    var e_1, _a;
    var loggerType = logOptions.logger;
    if (!loggerType) {
        return function () { };
    }
    var logger;
    if (typeof loggerType === 'string') {
        logger = win[loggerType];
    }
    else {
        logger = loggerType;
    }
    var logCount = 0;
    var cancelHandlers = [];
    if (logOptions.level.includes('error')) {
        if (window) {
            var errorHandler_1 = function (event) {
                var message = event.message, error = event.error;
                var trace = errorStackParser.ErrorStackParser.parse(error).map(function (stackFrame) { return stackFrame.toString(); });
                var payload = [stringify.stringify(message, logOptions.stringifyOptions)];
                cb({
                    level: 'error',
                    trace: trace,
                    payload: payload,
                });
            };
            window.addEventListener('error', errorHandler_1);
            cancelHandlers.push(function () {
                if (window)
                    window.removeEventListener('error', errorHandler_1);
            });
        }
    }
    try {
        for (var _b = tslib_es6.__values(logOptions.level), _c = _b.next(); !_c.done; _c = _b.next()) {
            var levelType = _c.value;
            cancelHandlers.push(replace(logger, levelType));
        }
    }
    catch (e_1_1) { e_1 = { error: e_1_1 }; }
    finally {
        try {
            if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
        }
        finally { if (e_1) throw e_1.error; }
    }
    return function () {
        cancelHandlers.forEach(function (h) { return h(); });
    };
    function replace(_logger, level) {
        var _this = this;
        if (!_logger[level]) {
            return function () { };
        }
        return utils.patch(_logger, level, function (original) {
            return function () {
                var args = [];
                for (var _i = 0; _i < arguments.length; _i++) {
                    args[_i] = arguments[_i];
                }
                original.apply(_this, args);
                try {
                    var trace = errorStackParser.ErrorStackParser.parse(new Error())
                        .map(function (stackFrame) { return stackFrame.toString(); })
                        .splice(1);
                    var payload = args.map(function (s) {
                        return stringify.stringify(s, logOptions.stringifyOptions);
                    });
                    logCount++;
                    if (logCount < logOptions.lengthThreshold) {
                        cb({
                            level: level,
                            trace: trace,
                            payload: payload,
                        });
                    }
                    else if (logCount === logOptions.lengthThreshold) {
                        cb({
                            level: 'warn',
                            trace: [],
                            payload: [
                                stringify.stringify('The number of log records reached the threshold.'),
                            ],
                        });
                    }
                }
                catch (error) {
                    original.apply(void 0, tslib_es6.__spreadArray(['rrweb logger error:', error], tslib_es6.__read(args), false));
                }
            };
        });
    }
}
var PLUGIN_NAME = 'rrweb/console@1';
var getRecordConsolePlugin = function (options) { return ({
    name: PLUGIN_NAME,
    observer: initLogObserver,
    options: options
        ? Object.assign({}, defaultLogOptions, options)
        : defaultLogOptions,
}); };

exports.PLUGIN_NAME = PLUGIN_NAME;
exports.getRecordConsolePlugin = getRecordConsolePlugin;


},{"../../../../ext/tslib/tslib.es6.js":55,"../../../utils.js":85,"./error-stack-parser.js":61,"./stringify.js":63}],63:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');

function pathToSelector(node) {
    if (!node || !node.outerHTML) {
        return '';
    }
    var path = '';
    while (node.parentElement) {
        var name_1 = node.localName;
        if (!name_1) {
            break;
        }
        name_1 = name_1.toLowerCase();
        var parent_1 = node.parentElement;
        var domSiblings = [];
        if (parent_1.children && parent_1.children.length > 0) {
            for (var i = 0; i < parent_1.children.length; i++) {
                var sibling = parent_1.children[i];
                if (sibling.localName && sibling.localName.toLowerCase) {
                    if (sibling.localName.toLowerCase() === name_1) {
                        domSiblings.push(sibling);
                    }
                }
            }
        }
        if (domSiblings.length > 1) {
            name_1 += ':eq(' + domSiblings.indexOf(node) + ')';
        }
        path = name_1 + (path ? '>' + path : '');
        node = parent_1;
    }
    return path;
}
function isObject(obj) {
    return Object.prototype.toString.call(obj) === '[object Object]';
}
function isObjTooDeep(obj, limit) {
    var e_1, _a;
    if (limit === 0) {
        return true;
    }
    var keys = Object.keys(obj);
    try {
        for (var keys_1 = tslib_es6.__values(keys), keys_1_1 = keys_1.next(); !keys_1_1.done; keys_1_1 = keys_1.next()) {
            var key = keys_1_1.value;
            if (isObject(obj[key]) && isObjTooDeep(obj[key], limit - 1)) {
                return true;
            }
        }
    }
    catch (e_1_1) { e_1 = { error: e_1_1 }; }
    finally {
        try {
            if (keys_1_1 && !keys_1_1.done && (_a = keys_1.return)) _a.call(keys_1);
        }
        finally { if (e_1) throw e_1.error; }
    }
    return false;
}
function stringify(obj, stringifyOptions) {
    var options = {
        numOfKeysLimit: 50,
        depthOfLimit: 4,
    };
    Object.assign(options, stringifyOptions);
    var stack = [];
    var keys = [];
    return JSON.stringify(obj, function (key, value) {
        if (stack.length > 0) {
            var thisPos = stack.indexOf(this);
            ~thisPos ? stack.splice(thisPos + 1) : stack.push(this);
            ~thisPos ? keys.splice(thisPos, Infinity, key) : keys.push(key);
            if (~stack.indexOf(value)) {
                if (stack[0] === value) {
                    value = '[Circular ~]';
                }
                else {
                    value =
                        '[Circular ~.' +
                            keys.slice(0, stack.indexOf(value)).join('.') +
                            ']';
                }
            }
        }
        else {
            stack.push(value);
        }
        if (value === null || value === undefined) {
            return value;
        }
        if (shouldIgnore(value)) {
            return toString(value);
        }
        if (value instanceof Event) {
            var eventResult = {};
            for (var eventKey in value) {
                var eventValue = value[eventKey];
                if (Array.isArray(eventValue)) {
                    eventResult[eventKey] = pathToSelector(eventValue.length ? eventValue[0] : null);
                }
                else {
                    eventResult[eventKey] = eventValue;
                }
            }
            return eventResult;
        }
        else if (value instanceof Node) {
            if (value instanceof HTMLElement) {
                return value ? value.outerHTML : '';
            }
            return value.nodeName;
        }
        else if (value instanceof Error) {
            return value.stack
                ? value.stack + '\nEnd of stack for Error object'
                : value.name + ': ' + value.message;
        }
        return value;
    });
    function shouldIgnore(_obj) {
        if (isObject(_obj) && Object.keys(_obj).length > options.numOfKeysLimit) {
            return true;
        }
        if (typeof _obj === 'function') {
            return true;
        }
        if (isObject(_obj) && isObjTooDeep(_obj, options.depthOfLimit)) {
            return true;
        }
        return false;
    }
    function toString(_obj) {
        var str = _obj.toString();
        if (options.stringLengthLimit && str.length > options.stringLengthLimit) {
            str = "".concat(str.slice(0, options.stringLengthLimit), "...");
        }
        return str;
    }
}

exports.stringify = stringify;


},{"../../../../ext/tslib/tslib.es6.js":55}],64:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');
const index = require('../record/index.js');
const types = require('../../../types.js');

var ORIGINAL_ATTRIBUTE_NAME = '__rrweb_original__';
var defaultLogConfig = {
    level: [
        'assert',
        'clear',
        'count',
        'countReset',
        'debug',
        'dir',
        'dirxml',
        'error',
        'group',
        'groupCollapsed',
        'groupEnd',
        'info',
        'log',
        'table',
        'time',
        'timeEnd',
        'timeLog',
        'trace',
        'warn',
    ],
    replayLogger: undefined,
};
var LogReplayPlugin = (function () {
    function LogReplayPlugin(config) {
        this.config = Object.assign(defaultLogConfig, config);
    }
    LogReplayPlugin.prototype.getConsoleLogger = function () {
        var e_1, _a;
        var _this = this;
        var replayLogger = {};
        var _loop_1 = function (level) {
            if (level === 'trace') {
                replayLogger[level] = function (data) {
                    var logger = console.log[ORIGINAL_ATTRIBUTE_NAME]
                        ? console.log[ORIGINAL_ATTRIBUTE_NAME]
                        : console.log;
                    logger.apply(void 0, tslib_es6.__spreadArray(tslib_es6.__spreadArray([], tslib_es6.__read(data.payload.map(function (s) { return JSON.parse(s); })), false), [_this.formatMessage(data)], false));
                };
            }
            else {
                replayLogger[level] = function (data) {
                    var logger = console[level][ORIGINAL_ATTRIBUTE_NAME]
                        ? console[level][ORIGINAL_ATTRIBUTE_NAME]
                        : console[level];
                    logger.apply(void 0, tslib_es6.__spreadArray(tslib_es6.__spreadArray([], tslib_es6.__read(data.payload.map(function (s) { return JSON.parse(s); })), false), [_this.formatMessage(data)], false));
                };
            }
        };
        try {
            for (var _b = tslib_es6.__values(this.config.level), _c = _b.next(); !_c.done; _c = _b.next()) {
                var level = _c.value;
                _loop_1(level);
            }
        }
        catch (e_1_1) { e_1 = { error: e_1_1 }; }
        finally {
            try {
                if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
            }
            finally { if (e_1) throw e_1.error; }
        }
        return replayLogger;
    };
    LogReplayPlugin.prototype.formatMessage = function (data) {
        if (data.trace.length === 0) {
            return '';
        }
        var stackPrefix = '\n\tat ';
        var result = stackPrefix;
        result += data.trace.join(stackPrefix);
        return result;
    };
    return LogReplayPlugin;
}());
var getReplayConsolePlugin = function (options) {
    var replayLogger = (options === null || options === void 0 ? void 0 : options.replayLogger) || new LogReplayPlugin(options).getConsoleLogger();
    return {
        handler: function (event, _isSync, context) {
            var logData = null;
            if (event.type === types.EventType.IncrementalSnapshot &&
                event.data.source === types.IncrementalSource.Log) {
                logData = event.data;
            }
            else if (event.type === types.EventType.Plugin &&
                event.data.plugin === index.PLUGIN_NAME) {
                logData = event.data.payload;
            }
            if (logData) {
                try {
                    if (typeof replayLogger[logData.level] === 'function') {
                        replayLogger[logData.level](logData);
                    }
                }
                catch (error) {
                    if (context.replayer.config.showWarning) {
                        console.warn(error);
                    }
                }
            }
        },
    };
};

exports.getReplayConsolePlugin = getReplayConsolePlugin;


},{"../../../../ext/tslib/tslib.es6.js":55,"../../../types.js":84,"../record/index.js":62}],65:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

var IframeManager = (function () {
    function IframeManager(options) {
        this.iframes = new WeakMap();
        this.mutationCb = options.mutationCb;
    }
    IframeManager.prototype.addIframe = function (iframeEl) {
        this.iframes.set(iframeEl, true);
    };
    IframeManager.prototype.addLoadListener = function (cb) {
        this.loadListener = cb;
    };
    IframeManager.prototype.attachIframe = function (iframeEl, childSn) {
        var _a;
        this.mutationCb({
            adds: [
                {
                    parentId: iframeEl.__sn.id,
                    nextId: null,
                    node: childSn,
                },
            ],
            removes: [],
            texts: [],
            attributes: [],
            isAttachIframe: true,
        });
        (_a = this.loadListener) === null || _a === void 0 ? void 0 : _a.call(this, iframeEl);
    };
    return IframeManager;
}());

exports.IframeManager = IframeManager;


},{}],66:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');
const rrwebSnapshot = require('../../../rrweb-snapshot/es/rrweb-snapshot.js');
const observer = require('./observer.js');
const utils = require('../utils.js');
const types = require('../types.js');
const iframeManager = require('./iframe-manager.js');
const shadowDomManager = require('./shadow-dom-manager.js');
const canvasManager = require('./observers/canvas/canvas-manager.js');

function wrapEvent(e) {
    return tslib_es6.__assign(tslib_es6.__assign({}, e), { timestamp: Date.now() });
}
var wrappedEmit;
var takeFullSnapshot;
var mirror = utils.createMirror();
function record(options) {
    if (options === void 0) { options = {}; }
    var emit = options.emit, checkoutEveryNms = options.checkoutEveryNms, checkoutEveryNth = options.checkoutEveryNth, _a = options.blockClass, blockClass = _a === void 0 ? 'rr-block' : _a, _b = options.blockSelector, blockSelector = _b === void 0 ? null : _b, _c = options.ignoreClass, ignoreClass = _c === void 0 ? 'rr-ignore' : _c, _d = options.maskTextClass, maskTextClass = _d === void 0 ? 'rr-mask' : _d, _e = options.maskTextSelector, maskTextSelector = _e === void 0 ? null : _e, _f = options.inlineStylesheet, inlineStylesheet = _f === void 0 ? true : _f, maskAllInputs = options.maskAllInputs, _maskInputOptions = options.maskInputOptions, _slimDOMOptions = options.slimDOMOptions, maskInputFn = options.maskInputFn, maskTextFn = options.maskTextFn, hooks = options.hooks, packFn = options.packFn, _g = options.sampling, sampling = _g === void 0 ? {} : _g, mousemoveWait = options.mousemoveWait, _h = options.recordCanvas, recordCanvas = _h === void 0 ? false : _h, _j = options.userTriggeredOnInput, userTriggeredOnInput = _j === void 0 ? false : _j, _k = options.collectFonts, collectFonts = _k === void 0 ? false : _k, _l = options.inlineImages, inlineImages = _l === void 0 ? false : _l, plugins = options.plugins, _m = options.keepIframeSrcFn, keepIframeSrcFn = _m === void 0 ? function () { return false; } : _m;
    if (!emit) {
        throw new Error('emit function is required');
    }
    if (mousemoveWait !== undefined && sampling.mousemove === undefined) {
        sampling.mousemove = mousemoveWait;
    }
    var maskInputOptions = maskAllInputs === true
        ? {
            color: true,
            date: true,
            'datetime-local': true,
            email: true,
            month: true,
            number: true,
            range: true,
            search: true,
            tel: true,
            text: true,
            time: true,
            url: true,
            week: true,
            textarea: true,
            select: true,
            password: true,
        }
        : _maskInputOptions !== undefined
            ? _maskInputOptions
            : { password: true };
    var slimDOMOptions = _slimDOMOptions === true || _slimDOMOptions === 'all'
        ? {
            script: true,
            comment: true,
            headFavicon: true,
            headWhitespace: true,
            headMetaSocial: true,
            headMetaRobots: true,
            headMetaHttpEquiv: true,
            headMetaVerification: true,
            headMetaAuthorship: _slimDOMOptions === 'all',
            headMetaDescKeywords: _slimDOMOptions === 'all',
        }
        : _slimDOMOptions
            ? _slimDOMOptions
            : {};
    utils.polyfill();
    var lastFullSnapshotEvent;
    var incrementalSnapshotCount = 0;
    var eventProcessor = function (e) {
        var e_1, _a;
        try {
            for (var _b = tslib_es6.__values(plugins || []), _c = _b.next(); !_c.done; _c = _b.next()) {
                var plugin = _c.value;
                if (plugin.eventProcessor) {
                    e = plugin.eventProcessor(e);
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
        if (packFn) {
            e = packFn(e);
        }
        return e;
    };
    wrappedEmit = function (e, isCheckout) {
        var _a;
        if (((_a = observer.mutationBuffers[0]) === null || _a === void 0 ? void 0 : _a.isFrozen()) &&
            e.type !== types.EventType.FullSnapshot &&
            !(e.type === types.EventType.IncrementalSnapshot &&
                e.data.source === types.IncrementalSource.Mutation)) {
            observer.mutationBuffers.forEach(function (buf) { return buf.unfreeze(); });
        }
        emit(eventProcessor(e), isCheckout);
        if (e.type === types.EventType.FullSnapshot) {
            lastFullSnapshotEvent = e;
            incrementalSnapshotCount = 0;
        }
        else if (e.type === types.EventType.IncrementalSnapshot) {
            if (e.data.source === types.IncrementalSource.Mutation &&
                e.data.isAttachIframe) {
                return;
            }
            incrementalSnapshotCount++;
            var exceedCount = checkoutEveryNth && incrementalSnapshotCount >= checkoutEveryNth;
            var exceedTime = checkoutEveryNms &&
                e.timestamp - lastFullSnapshotEvent.timestamp > checkoutEveryNms;
            if (exceedCount || exceedTime) {
                takeFullSnapshot(true);
            }
        }
    };
    var wrappedMutationEmit = function (m) {
        wrappedEmit(wrapEvent({
            type: types.EventType.IncrementalSnapshot,
            data: tslib_es6.__assign({ source: types.IncrementalSource.Mutation }, m),
        }));
    };
    var wrappedScrollEmit = function (p) {
        return wrappedEmit(wrapEvent({
            type: types.EventType.IncrementalSnapshot,
            data: tslib_es6.__assign({ source: types.IncrementalSource.Scroll }, p),
        }));
    };
    var wrappedCanvasMutationEmit = function (p) {
        return wrappedEmit(wrapEvent({
            type: types.EventType.IncrementalSnapshot,
            data: tslib_es6.__assign({ source: types.IncrementalSource.CanvasMutation }, p),
        }));
    };
    var iframeManager$1 = new iframeManager.IframeManager({
        mutationCb: wrappedMutationEmit,
    });
    var canvasManager$1 = new canvasManager.CanvasManager({
        recordCanvas: recordCanvas,
        mutationCb: wrappedCanvasMutationEmit,
        win: window,
        blockClass: blockClass,
        mirror: mirror,
    });
    var shadowDomManager$1 = new shadowDomManager.ShadowDomManager({
        mutationCb: wrappedMutationEmit,
        scrollCb: wrappedScrollEmit,
        bypassOptions: {
            blockClass: blockClass,
            blockSelector: blockSelector,
            maskTextClass: maskTextClass,
            maskTextSelector: maskTextSelector,
            inlineStylesheet: inlineStylesheet,
            maskInputOptions: maskInputOptions,
            maskTextFn: maskTextFn,
            maskInputFn: maskInputFn,
            recordCanvas: recordCanvas,
            inlineImages: inlineImages,
            sampling: sampling,
            slimDOMOptions: slimDOMOptions,
            iframeManager: iframeManager$1,
            canvasManager: canvasManager$1,
        },
        mirror: mirror,
    });
    takeFullSnapshot = function (isCheckout) {
        var _a, _b, _c, _d;
        if (isCheckout === void 0) { isCheckout = false; }
        wrappedEmit(wrapEvent({
            type: types.EventType.Meta,
            data: {
                href: window.location.href,
                width: utils.getWindowWidth(),
                height: utils.getWindowHeight(),
            },
        }), isCheckout);
        observer.mutationBuffers.forEach(function (buf) { return buf.lock(); });
        var _e = tslib_es6.__read(rrwebSnapshot.snapshot(document, {
            blockClass: blockClass,
            blockSelector: blockSelector,
            maskTextClass: maskTextClass,
            maskTextSelector: maskTextSelector,
            inlineStylesheet: inlineStylesheet,
            maskAllInputs: maskInputOptions,
            maskTextFn: maskTextFn,
            slimDOM: slimDOMOptions,
            recordCanvas: recordCanvas,
            inlineImages: inlineImages,
            onSerialize: function (n) {
                if (utils.isIframeINode(n)) {
                    iframeManager$1.addIframe(n);
                }
                if (utils.hasShadowRoot(n)) {
                    shadowDomManager$1.addShadowRoot(n.shadowRoot, document);
                }
            },
            onIframeLoad: function (iframe, childSn) {
                iframeManager$1.attachIframe(iframe, childSn);
                shadowDomManager$1.observeAttachShadow(iframe);
            },
            keepIframeSrcFn: keepIframeSrcFn,
        }), 2), node = _e[0], idNodeMap = _e[1];
        if (!node) {
            return console.warn('Failed to snapshot the document');
        }
        mirror.map = idNodeMap;
        wrappedEmit(wrapEvent({
            type: types.EventType.FullSnapshot,
            data: {
                node: node,
                initialOffset: {
                    left: window.pageXOffset !== undefined
                        ? window.pageXOffset
                        : (document === null || document === void 0 ? void 0 : document.documentElement.scrollLeft) ||
                            ((_b = (_a = document === null || document === void 0 ? void 0 : document.body) === null || _a === void 0 ? void 0 : _a.parentElement) === null || _b === void 0 ? void 0 : _b.scrollLeft) ||
                            (document === null || document === void 0 ? void 0 : document.body.scrollLeft) ||
                            0,
                    top: window.pageYOffset !== undefined
                        ? window.pageYOffset
                        : (document === null || document === void 0 ? void 0 : document.documentElement.scrollTop) ||
                            ((_d = (_c = document === null || document === void 0 ? void 0 : document.body) === null || _c === void 0 ? void 0 : _c.parentElement) === null || _d === void 0 ? void 0 : _d.scrollTop) ||
                            (document === null || document === void 0 ? void 0 : document.body.scrollTop) ||
                            0,
                },
            },
        }));
        observer.mutationBuffers.forEach(function (buf) { return buf.unlock(); });
    };
    try {
        var handlers_1 = [];
        handlers_1.push(utils.on('DOMContentLoaded', function () {
            wrappedEmit(wrapEvent({
                type: types.EventType.DomContentLoaded,
                data: {},
            }));
        }));
        var observe_1 = function (doc) {
            var _a;
            return observer.initObservers({
                mutationCb: wrappedMutationEmit,
                mousemoveCb: function (positions, source) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: {
                            source: source,
                            positions: positions,
                        },
                    }));
                },
                mouseInteractionCb: function (d) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: tslib_es6.__assign({ source: types.IncrementalSource.MouseInteraction }, d),
                    }));
                },
                scrollCb: wrappedScrollEmit,
                viewportResizeCb: function (d) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: tslib_es6.__assign({ source: types.IncrementalSource.ViewportResize }, d),
                    }));
                },
                inputCb: function (v) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: tslib_es6.__assign({ source: types.IncrementalSource.Input }, v),
                    }));
                },
                mediaInteractionCb: function (p) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: tslib_es6.__assign({ source: types.IncrementalSource.MediaInteraction }, p),
                    }));
                },
                styleSheetRuleCb: function (r) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: tslib_es6.__assign({ source: types.IncrementalSource.StyleSheetRule }, r),
                    }));
                },
                styleDeclarationCb: function (r) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: tslib_es6.__assign({ source: types.IncrementalSource.StyleDeclaration }, r),
                    }));
                },
                canvasMutationCb: wrappedCanvasMutationEmit,
                fontCb: function (p) {
                    return wrappedEmit(wrapEvent({
                        type: types.EventType.IncrementalSnapshot,
                        data: tslib_es6.__assign({ source: types.IncrementalSource.Font }, p),
                    }));
                },
                blockClass: blockClass,
                ignoreClass: ignoreClass,
                maskTextClass: maskTextClass,
                maskTextSelector: maskTextSelector,
                maskInputOptions: maskInputOptions,
                inlineStylesheet: inlineStylesheet,
                sampling: sampling,
                recordCanvas: recordCanvas,
                inlineImages: inlineImages,
                userTriggeredOnInput: userTriggeredOnInput,
                collectFonts: collectFonts,
                doc: doc,
                maskInputFn: maskInputFn,
                maskTextFn: maskTextFn,
                blockSelector: blockSelector,
                slimDOMOptions: slimDOMOptions,
                mirror: mirror,
                iframeManager: iframeManager$1,
                shadowDomManager: shadowDomManager$1,
                canvasManager: canvasManager$1,
                plugins: ((_a = plugins === null || plugins === void 0 ? void 0 : plugins.filter(function (p) { return p.observer; })) === null || _a === void 0 ? void 0 : _a.map(function (p) { return ({
                    observer: p.observer,
                    options: p.options,
                    callback: function (payload) {
                        return wrappedEmit(wrapEvent({
                            type: types.EventType.Plugin,
                            data: {
                                plugin: p.name,
                                payload: payload,
                            },
                        }));
                    },
                }); })) || [],
            }, hooks);
        };
        iframeManager$1.addLoadListener(function (iframeEl) {
            try {
                handlers_1.push(observe_1(iframeEl.contentDocument));
            } catch (error) {
                console.warn('error in rrweb iframe observer', error);
            }
        });
        var init_1 = function () {
            takeFullSnapshot();
            handlers_1.push(observe_1(document));
        };
        if (document.readyState === 'interactive' ||
            document.readyState === 'complete') {
            init_1();
        }
        else {
            handlers_1.push(utils.on('load', function () {
                wrappedEmit(wrapEvent({
                    type: types.EventType.Load,
                    data: {},
                }));
                init_1();
            }, window));
        }
        return function () {
            handlers_1.forEach(function (h) { return h(); });
        };
    }
    catch (error) {
        console.warn(error);
    }
}
record.addCustomEvent = function (tag, payload) {
    if (!wrappedEmit) {
        throw new Error('please add custom event after start recording');
    }
    wrappedEmit(wrapEvent({
        type: types.EventType.Custom,
        data: {
            tag: tag,
            payload: payload,
        },
    }));
};
record.freezePage = function () {
    observer.mutationBuffers.forEach(function (buf) { return buf.freeze(); });
};
record.takeFullSnapshot = function (isCheckout) {
    if (!takeFullSnapshot) {
        throw new Error('please take full snapshot after start recording');
    }
    takeFullSnapshot(isCheckout);
};
record.mirror = mirror;

exports.default = record;


},{"../../../rrweb-snapshot/es/rrweb-snapshot.js":54,"../../ext/tslib/tslib.es6.js":55,"../types.js":84,"../utils.js":85,"./iframe-manager.js":65,"./observer.js":68,"./observers/canvas/canvas-manager.js":70,"./shadow-dom-manager.js":74}],67:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');
const rrwebSnapshot = require('../../../rrweb-snapshot/es/rrweb-snapshot.js');
const utils = require('../utils.js');

function isNodeInLinkedList(n) {
    return '__ln' in n;
}
var DoubleLinkedList = (function () {
    function DoubleLinkedList() {
        this.length = 0;
        this.head = null;
    }
    DoubleLinkedList.prototype.get = function (position) {
        if (position >= this.length) {
            throw new Error('Position outside of list range');
        }
        var current = this.head;
        for (var index = 0; index < position; index++) {
            current = (current === null || current === void 0 ? void 0 : current.next) || null;
        }
        return current;
    };
    DoubleLinkedList.prototype.addNode = function (n) {
        var node = {
            value: n,
            previous: null,
            next: null,
        };
        n.__ln = node;
        if (n.previousSibling && isNodeInLinkedList(n.previousSibling)) {
            var current = n.previousSibling.__ln.next;
            node.next = current;
            node.previous = n.previousSibling.__ln;
            n.previousSibling.__ln.next = node;
            if (current) {
                current.previous = node;
            }
        }
        else if (n.nextSibling &&
            isNodeInLinkedList(n.nextSibling) &&
            n.nextSibling.__ln.previous) {
            var current = n.nextSibling.__ln.previous;
            node.previous = current;
            node.next = n.nextSibling.__ln;
            n.nextSibling.__ln.previous = node;
            if (current) {
                current.next = node;
            }
        }
        else {
            if (this.head) {
                this.head.previous = node;
            }
            node.next = this.head;
            this.head = node;
        }
        this.length++;
    };
    DoubleLinkedList.prototype.removeNode = function (n) {
        var current = n.__ln;
        if (!this.head) {
            return;
        }
        if (!current.previous) {
            this.head = current.next;
            if (this.head) {
                this.head.previous = null;
            }
        }
        else {
            current.previous.next = current.next;
            if (current.next) {
                current.next.previous = current.previous;
            }
        }
        if (n.__ln) {
            delete n.__ln;
        }
        this.length--;
    };
    return DoubleLinkedList;
}());
var moveKey = function (id, parentId) { return "".concat(id, "@").concat(parentId); };
function isINode(n) {
    return '__sn' in n;
}
var MutationBuffer = (function () {
    function MutationBuffer() {
        var _this = this;
        this.frozen = false;
        this.locked = false;
        this.texts = [];
        this.attributes = [];
        this.removes = [];
        this.mapRemoves = [];
        this.movedMap = {};
        this.addedSet = new Set();
        this.movedSet = new Set();
        this.droppedSet = new Set();
        this.processMutations = function (mutations) {
            mutations.forEach(_this.processMutation);
            _this.emit();
        };
        this.emit = function () {
            var e_1, _a, e_2, _b;
            if (_this.frozen || _this.locked) {
                return;
            }
            var adds = [];
            var addList = new DoubleLinkedList();
            var getNextId = function (n) {
                var ns = n;
                var nextId = rrwebSnapshot.IGNORED_NODE;
                while (nextId === rrwebSnapshot.IGNORED_NODE) {
                    ns = ns && ns.nextSibling;
                    nextId = ns && _this.mirror.getId(ns);
                }
                return nextId;
            };
            var pushAdd = function (n) {
                var _a, _b, _c, _d, _e;
                var shadowHost = n.getRootNode
                    ? (_a = n.getRootNode()) === null || _a === void 0 ? void 0 : _a.host
                    : null;
                var rootShadowHost = shadowHost;
                while ((_c = (_b = rootShadowHost === null || rootShadowHost === void 0 ? void 0 : rootShadowHost.getRootNode) === null || _b === void 0 ? void 0 : _b.call(rootShadowHost)) === null || _c === void 0 ? void 0 : _c.host)
                    rootShadowHost =
                        ((_e = (_d = rootShadowHost === null || rootShadowHost === void 0 ? void 0 : rootShadowHost.getRootNode) === null || _d === void 0 ? void 0 : _d.call(rootShadowHost)) === null || _e === void 0 ? void 0 : _e.host) ||
                            null;
                var notInDoc = !_this.doc.contains(n) &&
                    (rootShadowHost === null || !_this.doc.contains(rootShadowHost));
                if (!n.parentNode || notInDoc) {
                    return;
                }
                var parentId = rrwebSnapshot.isShadowRoot(n.parentNode)
                    ? _this.mirror.getId(shadowHost)
                    : _this.mirror.getId(n.parentNode);
                var nextId = getNextId(n);
                if (parentId === -1 || nextId === -1) {
                    return addList.addNode(n);
                }
                var sn = rrwebSnapshot.serializeNodeWithId(n, {
                    doc: _this.doc,
                    map: _this.mirror.map,
                    blockClass: _this.blockClass,
                    blockSelector: _this.blockSelector,
                    maskTextClass: _this.maskTextClass,
                    maskTextSelector: _this.maskTextSelector,
                    skipChild: true,
                    inlineStylesheet: _this.inlineStylesheet,
                    maskInputOptions: _this.maskInputOptions,
                    maskTextFn: _this.maskTextFn,
                    maskInputFn: _this.maskInputFn,
                    slimDOMOptions: _this.slimDOMOptions,
                    recordCanvas: _this.recordCanvas,
                    inlineImages: _this.inlineImages,
                    onSerialize: function (currentN) {
                        if (utils.isIframeINode(currentN)) {
                            _this.iframeManager.addIframe(currentN);
                        }
                        if (utils.hasShadowRoot(n)) {
                            _this.shadowDomManager.addShadowRoot(n.shadowRoot, document);
                        }
                    },
                    onIframeLoad: function (iframe, childSn) {
                        _this.iframeManager.attachIframe(iframe, childSn);
                        _this.shadowDomManager.observeAttachShadow(iframe);
                    },
                });
                if (sn) {
                    adds.push({
                        parentId: parentId,
                        nextId: nextId,
                        node: sn,
                    });
                }
            };
            while (_this.mapRemoves.length) {
                _this.mirror.removeNodeFromMap(_this.mapRemoves.shift());
            }
            try {
                for (var _c = tslib_es6.__values(_this.movedSet), _d = _c.next(); !_d.done; _d = _c.next()) {
                    var n = _d.value;
                    if (isParentRemoved(_this.removes, n, _this.mirror) &&
                        !_this.movedSet.has(n.parentNode)) {
                        continue;
                    }
                    pushAdd(n);
                }
            }
            catch (e_1_1) { e_1 = { error: e_1_1 }; }
            finally {
                try {
                    if (_d && !_d.done && (_a = _c.return)) _a.call(_c);
                }
                finally { if (e_1) throw e_1.error; }
            }
            try {
                for (var _e = tslib_es6.__values(_this.addedSet), _f = _e.next(); !_f.done; _f = _e.next()) {
                    var n = _f.value;
                    if (!isAncestorInSet(_this.droppedSet, n) &&
                        !isParentRemoved(_this.removes, n, _this.mirror)) {
                        pushAdd(n);
                    }
                    else if (isAncestorInSet(_this.movedSet, n)) {
                        pushAdd(n);
                    }
                    else {
                        _this.droppedSet.add(n);
                    }
                }
            }
            catch (e_2_1) { e_2 = { error: e_2_1 }; }
            finally {
                try {
                    if (_f && !_f.done && (_b = _e.return)) _b.call(_e);
                }
                finally { if (e_2) throw e_2.error; }
            }
            var candidate = null;
            while (addList.length) {
                var node = null;
                if (candidate) {
                    var parentId = _this.mirror.getId(candidate.value.parentNode);
                    var nextId = getNextId(candidate.value);
                    if (parentId !== -1 && nextId !== -1) {
                        node = candidate;
                    }
                }
                if (!node) {
                    for (var index = addList.length - 1; index >= 0; index--) {
                        var _node = addList.get(index);
                        if (_node) {
                            var parentId = _this.mirror.getId(_node.value.parentNode);
                            var nextId = getNextId(_node.value);
                            if (parentId !== -1 && nextId !== -1) {
                                node = _node;
                                break;
                            }
                        }
                    }
                }
                if (!node) {
                    while (addList.head) {
                        addList.removeNode(addList.head.value);
                    }
                    break;
                }
                candidate = node.previous;
                addList.removeNode(node.value);
                pushAdd(node.value);
            }
            var payload = {
                texts: _this.texts
                    .map(function (text) { return ({
                    id: _this.mirror.getId(text.node),
                    value: text.value,
                }); })
                    .filter(function (text) { return _this.mirror.has(text.id); }),
                attributes: _this.attributes
                    .map(function (attribute) { return ({
                    id: _this.mirror.getId(attribute.node),
                    attributes: attribute.attributes,
                }); })
                    .filter(function (attribute) { return _this.mirror.has(attribute.id); }),
                removes: _this.removes,
                adds: adds,
            };
            if (!payload.texts.length &&
                !payload.attributes.length &&
                !payload.removes.length &&
                !payload.adds.length) {
                return;
            }
            _this.texts = [];
            _this.attributes = [];
            _this.removes = [];
            _this.addedSet = new Set();
            _this.movedSet = new Set();
            _this.droppedSet = new Set();
            _this.movedMap = {};
            _this.mutationCb(payload);
        };
        this.processMutation = function (m) {
            var e_3, _a, e_4, _b;
            if (utils.isIgnored(m.target)) {
                return;
            }
            switch (m.type) {
                case 'characterData': {
                    var value = m.target.textContent;
                    if (!utils.isBlocked(m.target, _this.blockClass) && value !== m.oldValue) {
                        _this.texts.push({
                            value: rrwebSnapshot.needMaskingText(m.target, _this.maskTextClass, _this.maskTextSelector) && value
                                ? _this.maskTextFn
                                    ? _this.maskTextFn(value)
                                    : value.replace(/[\S]/g, '*')
                                : value,
                            node: m.target,
                        });
                    }
                    break;
                }
                case 'attributes': {
                    var target = m.target;
                    var value = m.target.getAttribute(m.attributeName);
                    if (m.attributeName === 'value') {
                        value = rrwebSnapshot.maskInputValue({
                            maskInputOptions: _this.maskInputOptions,
                            tagName: m.target.tagName,
                            type: m.target.getAttribute('type'),
                            value: value,
                            maskInputFn: _this.maskInputFn,
                        });
                    }
                    if (utils.isBlocked(m.target, _this.blockClass) || value === m.oldValue) {
                        return;
                    }
                    var item = _this.attributes.find(function (a) { return a.node === m.target; });
                    if (!item) {
                        item = {
                            node: m.target,
                            attributes: {},
                        };
                        _this.attributes.push(item);
                    }
                    if (m.attributeName === 'style') {
                        var old = _this.doc.createElement('span');
                        if (m.oldValue) {
                            old.setAttribute('style', m.oldValue);
                        }
                        if (item.attributes.style === undefined ||
                            item.attributes.style === null) {
                            item.attributes.style = {};
                        }
                        var styleObj = item.attributes.style;
                        try {
                            for (var _c = tslib_es6.__values(Array.from(target.style)), _d = _c.next(); !_d.done; _d = _c.next()) {
                                var pname = _d.value;
                                var newValue = target.style.getPropertyValue(pname);
                                var newPriority = target.style.getPropertyPriority(pname);
                                if (newValue !== old.style.getPropertyValue(pname) ||
                                    newPriority !== old.style.getPropertyPriority(pname)) {
                                    if (newPriority === '') {
                                        styleObj[pname] = newValue;
                                    }
                                    else {
                                        styleObj[pname] = [newValue, newPriority];
                                    }
                                }
                            }
                        }
                        catch (e_3_1) { e_3 = { error: e_3_1 }; }
                        finally {
                            try {
                                if (_d && !_d.done && (_a = _c.return)) _a.call(_c);
                            }
                            finally { if (e_3) throw e_3.error; }
                        }
                        try {
                            for (var _e = tslib_es6.__values(Array.from(old.style)), _f = _e.next(); !_f.done; _f = _e.next()) {
                                var pname = _f.value;
                                if (target.style.getPropertyValue(pname) === '') {
                                    styleObj[pname] = false;
                                }
                            }
                        }
                        catch (e_4_1) { e_4 = { error: e_4_1 }; }
                        finally {
                            try {
                                if (_f && !_f.done && (_b = _e.return)) _b.call(_e);
                            }
                            finally { if (e_4) throw e_4.error; }
                        }
                    }
                    else {
                        item.attributes[m.attributeName] = rrwebSnapshot.transformAttribute(_this.doc, m.target.tagName, m.attributeName, value);
                    }
                    break;
                }
                case 'childList': {
                    m.addedNodes.forEach(function (n) { return _this.genAdds(n, m.target); });
                    m.removedNodes.forEach(function (n) {
                        var nodeId = _this.mirror.getId(n);
                        var parentId = rrwebSnapshot.isShadowRoot(m.target)
                            ? _this.mirror.getId(m.target.host)
                            : _this.mirror.getId(m.target);
                        if (utils.isBlocked(m.target, _this.blockClass) || utils.isIgnored(n)) {
                            return;
                        }
                        if (_this.addedSet.has(n)) {
                            deepDelete(_this.addedSet, n);
                            _this.droppedSet.add(n);
                        }
                        else if (_this.addedSet.has(m.target) && nodeId === -1) ;
                        else if (utils.isAncestorRemoved(m.target, _this.mirror)) ;
                        else if (_this.movedSet.has(n) &&
                            _this.movedMap[moveKey(nodeId, parentId)]) {
                            deepDelete(_this.movedSet, n);
                        }
                        else {
                            _this.removes.push({
                                parentId: parentId,
                                id: nodeId,
                                isShadow: rrwebSnapshot.isShadowRoot(m.target) ? true : undefined,
                            });
                        }
                        _this.mapRemoves.push(n);
                    });
                    break;
                }
            }
        };
        this.genAdds = function (n, target) {
            if (target && utils.isBlocked(target, _this.blockClass)) {
                return;
            }
            if (isINode(n)) {
                if (utils.isIgnored(n)) {
                    return;
                }
                _this.movedSet.add(n);
                var targetId = null;
                if (target && isINode(target)) {
                    targetId = target.__sn.id;
                }
                if (targetId) {
                    _this.movedMap[moveKey(n.__sn.id, targetId)] = true;
                }
            }
            else {
                _this.addedSet.add(n);
                _this.droppedSet.delete(n);
            }
            if (!utils.isBlocked(n, _this.blockClass))
                n.childNodes.forEach(function (childN) { return _this.genAdds(childN); });
        };
    }
    MutationBuffer.prototype.init = function (options) {
        var _this = this;
        [
            'mutationCb',
            'blockClass',
            'blockSelector',
            'maskTextClass',
            'maskTextSelector',
            'inlineStylesheet',
            'maskInputOptions',
            'maskTextFn',
            'maskInputFn',
            'recordCanvas',
            'inlineImages',
            'slimDOMOptions',
            'doc',
            'mirror',
            'iframeManager',
            'shadowDomManager',
            'canvasManager',
        ].forEach(function (key) {
            _this[key] = options[key];
        });
    };
    MutationBuffer.prototype.freeze = function () {
        this.frozen = true;
        this.canvasManager.freeze();
    };
    MutationBuffer.prototype.unfreeze = function () {
        this.frozen = false;
        this.canvasManager.unfreeze();
        this.emit();
    };
    MutationBuffer.prototype.isFrozen = function () {
        return this.frozen;
    };
    MutationBuffer.prototype.lock = function () {
        this.locked = true;
        this.canvasManager.lock();
    };
    MutationBuffer.prototype.unlock = function () {
        this.locked = false;
        this.canvasManager.unlock();
        this.emit();
    };
    MutationBuffer.prototype.reset = function () {
        this.shadowDomManager.reset();
        this.canvasManager.reset();
    };
    return MutationBuffer;
}());
function deepDelete(addsSet, n) {
    addsSet.delete(n);
    n.childNodes.forEach(function (childN) { return deepDelete(addsSet, childN); });
}
function isParentRemoved(removes, n, mirror) {
    var parentNode = n.parentNode;
    if (!parentNode) {
        return false;
    }
    var parentId = mirror.getId(parentNode);
    if (removes.some(function (r) { return r.id === parentId; })) {
        return true;
    }
    return isParentRemoved(removes, parentNode, mirror);
}
function isAncestorInSet(set, n) {
    var parentNode = n.parentNode;
    if (!parentNode) {
        return false;
    }
    if (set.has(parentNode)) {
        return true;
    }
    return isAncestorInSet(set, parentNode);
}

exports.default = MutationBuffer;


},{"../../../rrweb-snapshot/es/rrweb-snapshot.js":54,"../../ext/tslib/tslib.es6.js":55,"../utils.js":85}],68:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');
const rrwebSnapshot = require('../../../rrweb-snapshot/es/rrweb-snapshot.js');
const utils = require('../utils.js');
const types = require('../types.js');
const mutation = require('./mutation.js');

var mutationBuffers = [];
var isCSSGroupingRuleSupported = typeof CSSGroupingRule !== 'undefined';
var isCSSMediaRuleSupported = typeof CSSMediaRule !== 'undefined';
var isCSSSupportsRuleSupported = typeof CSSSupportsRule !== 'undefined';
var isCSSConditionRuleSupported = typeof CSSConditionRule !== 'undefined';
function getEventTarget(event) {
    try {
        if ('composedPath' in event) {
            var path = event.composedPath();
            if (path.length) {
                return path[0];
            }
        }
        else if ('path' in event && event.path.length) {
            return event.path[0];
        }
        return event.target;
    }
    catch (_a) {
        return event.target;
    }
}
function initMutationObserver(options, rootEl) {
    var _a, _b;
    var mutationBuffer = new mutation.default();
    mutationBuffers.push(mutationBuffer);
    mutationBuffer.init(options);
    var mutationObserverCtor = window.MutationObserver ||
        window.__rrMutationObserver;
    var angularZoneSymbol = (_b = (_a = window === null || window === void 0 ? void 0 : window.Zone) === null || _a === void 0 ? void 0 : _a.__symbol__) === null || _b === void 0 ? void 0 : _b.call(_a, 'MutationObserver');
    if (angularZoneSymbol &&
        window[angularZoneSymbol]) {
        mutationObserverCtor = window[angularZoneSymbol];
    }
    var observer = new mutationObserverCtor(mutationBuffer.processMutations.bind(mutationBuffer));
    observer.observe(rootEl, {
        attributes: true,
        attributeOldValue: true,
        characterData: true,
        characterDataOldValue: true,
        childList: true,
        subtree: true,
    });
    return observer;
}
function initMoveObserver(_a) {
    var mousemoveCb = _a.mousemoveCb, sampling = _a.sampling, doc = _a.doc, mirror = _a.mirror;
    if (sampling.mousemove === false) {
        return function () { };
    }
    var threshold = typeof sampling.mousemove === 'number' ? sampling.mousemove : 50;
    var callbackThreshold = typeof sampling.mousemoveCallback === 'number'
        ? sampling.mousemoveCallback
        : 500;
    var positions = [];
    var timeBaseline;
    var wrappedCb = utils.throttle(function (source) {
        var totalOffset = Date.now() - timeBaseline;
        mousemoveCb(positions.map(function (p) {
            p.timeOffset -= totalOffset;
            return p;
        }), source);
        positions = [];
        timeBaseline = null;
    }, callbackThreshold);
    var updatePosition = utils.throttle(function (evt) {
        var target = getEventTarget(evt);
        var _a = utils.isTouchEvent(evt)
            ? evt.changedTouches[0]
            : evt, clientX = _a.clientX, clientY = _a.clientY;
        if (!timeBaseline) {
            timeBaseline = Date.now();
        }
        positions.push({
            x: clientX,
            y: clientY,
            id: mirror.getId(target),
            timeOffset: Date.now() - timeBaseline,
        });
        wrappedCb(typeof DragEvent !== 'undefined' && evt instanceof DragEvent
            ? types.IncrementalSource.Drag
            : evt instanceof MouseEvent
                ? types.IncrementalSource.MouseMove
                : types.IncrementalSource.TouchMove);
    }, threshold, {
        trailing: false,
    });
    var handlers = [
        utils.on('mousemove', updatePosition, doc),
        utils.on('touchmove', updatePosition, doc),
        utils.on('drag', updatePosition, doc),
    ];
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}
function initMouseInteractionObserver(_a) {
    var mouseInteractionCb = _a.mouseInteractionCb, doc = _a.doc, mirror = _a.mirror, blockClass = _a.blockClass, sampling = _a.sampling;
    if (sampling.mouseInteraction === false) {
        return function () { };
    }
    var disableMap = sampling.mouseInteraction === true ||
        sampling.mouseInteraction === undefined
        ? {}
        : sampling.mouseInteraction;
    var handlers = [];
    var getHandler = function (eventKey) {
        return function (event) {
            var target = getEventTarget(event);
            if (utils.isBlocked(target, blockClass)) {
                return;
            }
            var e = utils.isTouchEvent(event) ? event.changedTouches[0] : event;
            if (!e) {
                return;
            }
            var id = mirror.getId(target);
            var clientX = e.clientX, clientY = e.clientY;
            mouseInteractionCb({
                type: types.MouseInteractions[eventKey],
                id: id,
                x: clientX,
                y: clientY,
            });
        };
    };
    Object.keys(types.MouseInteractions)
        .filter(function (key) {
        return Number.isNaN(Number(key)) &&
            !key.endsWith('_Departed') &&
            disableMap[key] !== false;
    })
        .forEach(function (eventKey) {
        var eventName = eventKey.toLowerCase();
        var handler = getHandler(eventKey);
        handlers.push(utils.on(eventName, handler, doc));
    });
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}
function initScrollObserver(_a) {
    var scrollCb = _a.scrollCb, doc = _a.doc, mirror = _a.mirror, blockClass = _a.blockClass, sampling = _a.sampling;
    var updatePosition = utils.throttle(function (evt) {
        var target = getEventTarget(evt);
        if (!target || utils.isBlocked(target, blockClass)) {
            return;
        }
        var id = mirror.getId(target);
        if (target === doc) {
            var scrollEl = (doc.scrollingElement || doc.documentElement);
            scrollCb({
                id: id,
                x: scrollEl.scrollLeft,
                y: scrollEl.scrollTop,
            });
        }
        else {
            scrollCb({
                id: id,
                x: target.scrollLeft,
                y: target.scrollTop,
            });
        }
    }, sampling.scroll || 100);
    return utils.on('scroll', updatePosition, doc);
}
function initViewportResizeObserver(_a) {
    var viewportResizeCb = _a.viewportResizeCb;
    var lastH = -1;
    var lastW = -1;
    var updateDimension = utils.throttle(function () {
        var height = utils.getWindowHeight();
        var width = utils.getWindowWidth();
        if (lastH !== height || lastW !== width) {
            viewportResizeCb({
                width: Number(width),
                height: Number(height),
            });
            lastH = height;
            lastW = width;
        }
    }, 200);
    return utils.on('resize', updateDimension, window);
}
function wrapEventWithUserTriggeredFlag(v, enable) {
    var value = tslib_es6.__assign({}, v);
    if (!enable)
        delete value.userTriggered;
    return value;
}
var INPUT_TAGS = ['INPUT', 'TEXTAREA', 'SELECT'];
var lastInputValueMap = new WeakMap();
function initInputObserver(_a) {
    var inputCb = _a.inputCb, doc = _a.doc, mirror = _a.mirror, blockClass = _a.blockClass, ignoreClass = _a.ignoreClass, maskInputOptions = _a.maskInputOptions, maskInputFn = _a.maskInputFn, sampling = _a.sampling, userTriggeredOnInput = _a.userTriggeredOnInput;
    function eventHandler(event) {
        var target = getEventTarget(event);
        var userTriggered = event.isTrusted;
        if (target && target.tagName === 'OPTION')
            target = target.parentElement;
        if (!target ||
            !target.tagName ||
            INPUT_TAGS.indexOf(target.tagName) < 0 ||
            utils.isBlocked(target, blockClass)) {
            return;
        }
        var type = target.type;
        if (target.classList.contains(ignoreClass)) {
            return;
        }
        var text = target.value;
        var isChecked = false;
        if (type === 'radio' || type === 'checkbox') {
            isChecked = target.checked;
        }
        else if (maskInputOptions[target.tagName.toLowerCase()] ||
            maskInputOptions[type]) {
            text = rrwebSnapshot.maskInputValue({
                maskInputOptions: maskInputOptions,
                tagName: target.tagName,
                type: type,
                value: text,
                maskInputFn: maskInputFn,
            });
        }
        cbWithDedup(target, wrapEventWithUserTriggeredFlag({ text: text, isChecked: isChecked, userTriggered: userTriggered }, userTriggeredOnInput));
        var name = target.name;
        if (type === 'radio' && name && isChecked) {
            doc
                .querySelectorAll("input[type=\"radio\"][name=\"".concat(name, "\"]"))
                .forEach(function (el) {
                if (el !== target) {
                    cbWithDedup(el, wrapEventWithUserTriggeredFlag({
                        text: el.value,
                        isChecked: !isChecked,
                        userTriggered: false,
                    }, userTriggeredOnInput));
                }
            });
        }
    }
    function cbWithDedup(target, v) {
        var lastInputValue = lastInputValueMap.get(target);
        if (!lastInputValue ||
            lastInputValue.text !== v.text ||
            lastInputValue.isChecked !== v.isChecked) {
            lastInputValueMap.set(target, v);
            var id = mirror.getId(target);
            inputCb(tslib_es6.__assign(tslib_es6.__assign({}, v), { id: id }));
        }
    }
    var events = sampling.input === 'last' ? ['change'] : ['input', 'change'];
    var handlers = events.map(function (eventName) { return utils.on(eventName, eventHandler, doc); });
    var propertyDescriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    var hookProperties = [
        [HTMLInputElement.prototype, 'value'],
        [HTMLInputElement.prototype, 'checked'],
        [HTMLSelectElement.prototype, 'value'],
        [HTMLTextAreaElement.prototype, 'value'],
        [HTMLSelectElement.prototype, 'selectedIndex'],
        [HTMLOptionElement.prototype, 'selected'],
    ];
    if (propertyDescriptor && propertyDescriptor.set) {
        handlers.push.apply(handlers, tslib_es6.__spreadArray([], tslib_es6.__read(hookProperties.map(function (p) {
            return utils.hookSetter(p[0], p[1], {
                set: function () {
                    eventHandler({ target: this });
                },
            });
        })), false));
    }
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}
function getNestedCSSRulePositions(rule) {
    var positions = [];
    function recurse(childRule, pos) {
        if ((isCSSGroupingRuleSupported &&
            childRule.parentRule instanceof CSSGroupingRule) ||
            (isCSSMediaRuleSupported &&
                childRule.parentRule instanceof CSSMediaRule) ||
            (isCSSSupportsRuleSupported &&
                childRule.parentRule instanceof CSSSupportsRule) ||
            (isCSSConditionRuleSupported &&
                childRule.parentRule instanceof CSSConditionRule)) {
            var rules = Array.from(childRule.parentRule.cssRules);
            var index = rules.indexOf(childRule);
            pos.unshift(index);
        }
        else {
            var rules = Array.from(childRule.parentStyleSheet.cssRules);
            var index = rules.indexOf(childRule);
            pos.unshift(index);
        }
        return pos;
    }
    return recurse(rule, positions);
}
function initStyleSheetObserver(_a, _b) {
    var styleSheetRuleCb = _a.styleSheetRuleCb, mirror = _a.mirror;
    var win = _b.win;
    var insertRule = win.CSSStyleSheet.prototype.insertRule;
    win.CSSStyleSheet.prototype.insertRule = function (rule, index) {
        var id = mirror.getId(this.ownerNode);
        if (id !== -1) {
            styleSheetRuleCb({
                id: id,
                adds: [{ rule: rule, index: index }],
            });
        }
        return insertRule.apply(this, arguments);
    };
    var deleteRule = win.CSSStyleSheet.prototype.deleteRule;
    win.CSSStyleSheet.prototype.deleteRule = function (index) {
        var id = mirror.getId(this.ownerNode);
        if (id !== -1) {
            styleSheetRuleCb({
                id: id,
                removes: [{ index: index }],
            });
        }
        return deleteRule.apply(this, arguments);
    };
    var supportedNestedCSSRuleTypes = {};
    if (isCSSGroupingRuleSupported) {
        supportedNestedCSSRuleTypes.CSSGroupingRule = win.CSSGroupingRule;
    }
    else {
        if (isCSSMediaRuleSupported) {
            supportedNestedCSSRuleTypes.CSSMediaRule = win.CSSMediaRule;
        }
        if (isCSSConditionRuleSupported) {
            supportedNestedCSSRuleTypes.CSSConditionRule = win.CSSConditionRule;
        }
        if (isCSSSupportsRuleSupported) {
            supportedNestedCSSRuleTypes.CSSSupportsRule = win.CSSSupportsRule;
        }
    }
    var unmodifiedFunctions = {};
    Object.entries(supportedNestedCSSRuleTypes).forEach(function (_a) {
        var _b = tslib_es6.__read(_a, 2), typeKey = _b[0], type = _b[1];
        unmodifiedFunctions[typeKey] = {
            insertRule: type.prototype.insertRule,
            deleteRule: type.prototype.deleteRule,
        };
        type.prototype.insertRule = function (rule, index) {
            var id = mirror.getId(this.parentStyleSheet.ownerNode);
            if (id !== -1) {
                styleSheetRuleCb({
                    id: id,
                    adds: [
                        {
                            rule: rule,
                            index: tslib_es6.__spreadArray(tslib_es6.__spreadArray([], tslib_es6.__read(getNestedCSSRulePositions(this)), false), [
                                index || 0,
                            ], false),
                        },
                    ],
                });
            }
            return unmodifiedFunctions[typeKey].insertRule.apply(this, arguments);
        };
        type.prototype.deleteRule = function (index) {
            var id = mirror.getId(this.parentStyleSheet.ownerNode);
            if (id !== -1) {
                styleSheetRuleCb({
                    id: id,
                    removes: [{ index: tslib_es6.__spreadArray(tslib_es6.__spreadArray([], tslib_es6.__read(getNestedCSSRulePositions(this)), false), [index], false) }],
                });
            }
            return unmodifiedFunctions[typeKey].deleteRule.apply(this, arguments);
        };
    });
    return function () {
        win.CSSStyleSheet.prototype.insertRule = insertRule;
        win.CSSStyleSheet.prototype.deleteRule = deleteRule;
        Object.entries(supportedNestedCSSRuleTypes).forEach(function (_a) {
            var _b = tslib_es6.__read(_a, 2), typeKey = _b[0], type = _b[1];
            type.prototype.insertRule = unmodifiedFunctions[typeKey].insertRule;
            type.prototype.deleteRule = unmodifiedFunctions[typeKey].deleteRule;
        });
    };
}
function initStyleDeclarationObserver(_a, _b) {
    var styleDeclarationCb = _a.styleDeclarationCb, mirror = _a.mirror;
    var win = _b.win;
    var setProperty = win.CSSStyleDeclaration.prototype.setProperty;
    win.CSSStyleDeclaration.prototype.setProperty = function (property, value, priority) {
        var _a, _b;
        var id = mirror.getId((_b = (_a = this.parentRule) === null || _a === void 0 ? void 0 : _a.parentStyleSheet) === null || _b === void 0 ? void 0 : _b.ownerNode);
        if (id !== -1) {
            styleDeclarationCb({
                id: id,
                set: {
                    property: property,
                    value: value,
                    priority: priority,
                },
                index: getNestedCSSRulePositions(this.parentRule),
            });
        }
        return setProperty.apply(this, arguments);
    };
    var removeProperty = win.CSSStyleDeclaration.prototype.removeProperty;
    win.CSSStyleDeclaration.prototype.removeProperty = function (property) {
        var _a, _b;
        var id = mirror.getId((_b = (_a = this.parentRule) === null || _a === void 0 ? void 0 : _a.parentStyleSheet) === null || _b === void 0 ? void 0 : _b.ownerNode);
        if (id !== -1) {
            styleDeclarationCb({
                id: id,
                remove: {
                    property: property,
                },
                index: getNestedCSSRulePositions(this.parentRule),
            });
        }
        return removeProperty.apply(this, arguments);
    };
    return function () {
        win.CSSStyleDeclaration.prototype.setProperty = setProperty;
        win.CSSStyleDeclaration.prototype.removeProperty = removeProperty;
    };
}
function initMediaInteractionObserver(_a) {
    var mediaInteractionCb = _a.mediaInteractionCb, blockClass = _a.blockClass, mirror = _a.mirror, sampling = _a.sampling;
    var handler = function (type) {
        return utils.throttle(function (event) {
            var target = getEventTarget(event);
            if (!target || utils.isBlocked(target, blockClass)) {
                return;
            }
            var _a = target, currentTime = _a.currentTime, volume = _a.volume, muted = _a.muted;
            mediaInteractionCb({
                type: type,
                id: mirror.getId(target),
                currentTime: currentTime,
                volume: volume,
                muted: muted,
            });
        }, sampling.media || 500);
    };
    var handlers = [
        utils.on('play', handler(0)),
        utils.on('pause', handler(1)),
        utils.on('seeked', handler(2)),
        utils.on('volumechange', handler(3)),
    ];
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}
function initFontObserver(_a) {
    var fontCb = _a.fontCb, doc = _a.doc;
    var win = doc.defaultView;
    if (!win) {
        return function () { };
    }
    var handlers = [];
    var fontMap = new WeakMap();
    var originalFontFace = win.FontFace;
    win.FontFace = function FontFace(family, source, descriptors) {
        var fontFace = new originalFontFace(family, source, descriptors);
        fontMap.set(fontFace, {
            family: family,
            buffer: typeof source !== 'string',
            descriptors: descriptors,
            fontSource: typeof source === 'string'
                ? source
                :
                    JSON.stringify(Array.from(new Uint8Array(source))),
        });
        return fontFace;
    };
    var restoreHandler = utils.patch(doc.fonts, 'add', function (original) {
        return function (fontFace) {
            setTimeout(function () {
                var p = fontMap.get(fontFace);
                if (p) {
                    fontCb(p);
                    fontMap.delete(fontFace);
                }
            }, 0);
            return original.apply(this, [fontFace]);
        };
    });
    handlers.push(function () {
        win.FontFace = originalFontFace;
    });
    handlers.push(restoreHandler);
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}
function mergeHooks(o, hooks) {
    var mutationCb = o.mutationCb, mousemoveCb = o.mousemoveCb, mouseInteractionCb = o.mouseInteractionCb, scrollCb = o.scrollCb, viewportResizeCb = o.viewportResizeCb, inputCb = o.inputCb, mediaInteractionCb = o.mediaInteractionCb, styleSheetRuleCb = o.styleSheetRuleCb, styleDeclarationCb = o.styleDeclarationCb, canvasMutationCb = o.canvasMutationCb, fontCb = o.fontCb;
    o.mutationCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.mutation) {
            hooks.mutation.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        mutationCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.mousemoveCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.mousemove) {
            hooks.mousemove.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        mousemoveCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.mouseInteractionCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.mouseInteraction) {
            hooks.mouseInteraction.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        mouseInteractionCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.scrollCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.scroll) {
            hooks.scroll.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        scrollCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.viewportResizeCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.viewportResize) {
            hooks.viewportResize.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        viewportResizeCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.inputCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.input) {
            hooks.input.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        inputCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.mediaInteractionCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.mediaInteaction) {
            hooks.mediaInteaction.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        mediaInteractionCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.styleSheetRuleCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.styleSheetRule) {
            hooks.styleSheetRule.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        styleSheetRuleCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.styleDeclarationCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.styleDeclaration) {
            hooks.styleDeclaration.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        styleDeclarationCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.canvasMutationCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.canvasMutation) {
            hooks.canvasMutation.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        canvasMutationCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
    o.fontCb = function () {
        var p = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            p[_i] = arguments[_i];
        }
        if (hooks.font) {
            hooks.font.apply(hooks, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
        }
        fontCb.apply(void 0, tslib_es6.__spreadArray([], tslib_es6.__read(p), false));
    };
}
function initObservers(o, hooks) {
    var e_1, _a;
    if (hooks === void 0) { hooks = {}; }
    var currentWindow = o.doc.defaultView;
    if (!currentWindow) {
        return function () { };
    }
    mergeHooks(o, hooks);
    var mutationObserver = initMutationObserver(o, o.doc);
    var mousemoveHandler = initMoveObserver(o);
    var mouseInteractionHandler = initMouseInteractionObserver(o);
    var scrollHandler = initScrollObserver(o);
    var viewportResizeHandler = initViewportResizeObserver(o);
    var inputHandler = initInputObserver(o);
    var mediaInteractionHandler = initMediaInteractionObserver(o);
    var styleSheetObserver = initStyleSheetObserver(o, { win: currentWindow });
    var styleDeclarationObserver = initStyleDeclarationObserver(o, {
        win: currentWindow,
    });
    var fontObserver = o.collectFonts ? initFontObserver(o) : function () { };
    var pluginHandlers = [];
    try {
        for (var _b = tslib_es6.__values(o.plugins), _c = _b.next(); !_c.done; _c = _b.next()) {
            var plugin = _c.value;
            pluginHandlers.push(plugin.observer(plugin.callback, currentWindow, plugin.options));
        }
    }
    catch (e_1_1) { e_1 = { error: e_1_1 }; }
    finally {
        try {
            if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
        }
        finally { if (e_1) throw e_1.error; }
    }
    return function () {
        mutationBuffers.forEach(function (b) { return b.reset(); });
        mutationObserver.disconnect();
        mousemoveHandler();
        mouseInteractionHandler();
        scrollHandler();
        viewportResizeHandler();
        inputHandler();
        mediaInteractionHandler();
        styleSheetObserver();
        styleDeclarationObserver();
        fontObserver();
        pluginHandlers.forEach(function (h) { return h(); });
    };
}

exports.INPUT_TAGS = INPUT_TAGS;
exports.initMutationObserver = initMutationObserver;
exports.initObservers = initObservers;
exports.initScrollObserver = initScrollObserver;
exports.mutationBuffers = mutationBuffers;


},{"../../../rrweb-snapshot/es/rrweb-snapshot.js":54,"../../ext/tslib/tslib.es6.js":55,"../types.js":84,"../utils.js":85,"./mutation.js":67}],69:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');
const types = require('../../../types.js');
const utils = require('../../../utils.js');

function initCanvas2DMutationObserver(cb, win, blockClass, mirror) {
    var e_1, _a;
    var handlers = [];
    var props2D = Object.getOwnPropertyNames(win.CanvasRenderingContext2D.prototype);
    var _loop_1 = function (prop) {
        try {
            if (typeof win.CanvasRenderingContext2D.prototype[prop] !== 'function') {
                return "continue";
            }
            var restoreHandler = utils.patch(win.CanvasRenderingContext2D.prototype, prop, function (original) {
                return function () {
                    var _this = this;
                    var args = [];
                    for (var _i = 0; _i < arguments.length; _i++) {
                        args[_i] = arguments[_i];
                    }
                    if (!utils.isBlocked(this.canvas, blockClass)) {
                        setTimeout(function () {
                            var recordArgs = tslib_es6.__spreadArray([], tslib_es6.__read(args), false);
                            if (prop === 'drawImage') {
                                if (recordArgs[0] &&
                                    recordArgs[0] instanceof HTMLCanvasElement) {
                                    var canvas = recordArgs[0];
                                    var ctx = canvas.getContext('2d');
                                    var imgd = ctx === null || ctx === void 0 ? void 0 : ctx.getImageData(0, 0, canvas.width, canvas.height);
                                    var pix = imgd === null || imgd === void 0 ? void 0 : imgd.data;
                                    recordArgs[0] = JSON.stringify(pix);
                                }
                            }
                            cb(_this.canvas, {
                                type: types.CanvasContext['2D'],
                                property: prop,
                                args: recordArgs,
                            });
                        }, 0);
                    }
                    return original.apply(this, args);
                };
            });
            handlers.push(restoreHandler);
        }
        catch (_b) {
            var hookHandler = utils.hookSetter(win.CanvasRenderingContext2D.prototype, prop, {
                set: function (v) {
                    cb(this.canvas, {
                        type: types.CanvasContext['2D'],
                        property: prop,
                        args: [v],
                        setter: true,
                    });
                },
            });
            handlers.push(hookHandler);
        }
    };
    try {
        for (var props2D_1 = tslib_es6.__values(props2D), props2D_1_1 = props2D_1.next(); !props2D_1_1.done; props2D_1_1 = props2D_1.next()) {
            var prop = props2D_1_1.value;
            _loop_1(prop);
        }
    }
    catch (e_1_1) { e_1 = { error: e_1_1 }; }
    finally {
        try {
            if (props2D_1_1 && !props2D_1_1.done && (_a = props2D_1.return)) _a.call(props2D_1);
        }
        finally { if (e_1) throw e_1.error; }
    }
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}

exports.default = initCanvas2DMutationObserver;


},{"../../../../ext/tslib/tslib.es6.js":55,"../../../types.js":84,"../../../utils.js":85}],70:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');
const _2d = require('./2d.js');
const canvas = require('./canvas.js');
const webgl = require('./webgl.js');

var CanvasManager = (function () {
    function CanvasManager(options) {
        this.pendingCanvasMutations = new Map();
        this.rafStamps = { latestId: 0, invokeId: null };
        this.frozen = false;
        this.locked = false;
        this.processMutation = function (target, mutation) {
            var newFrame = this.rafStamps.invokeId &&
                this.rafStamps.latestId !== this.rafStamps.invokeId;
            if (newFrame || !this.rafStamps.invokeId)
                this.rafStamps.invokeId = this.rafStamps.latestId;
            if (!this.pendingCanvasMutations.has(target)) {
                this.pendingCanvasMutations.set(target, []);
            }
            this.pendingCanvasMutations.get(target).push(mutation);
        };
        this.mutationCb = options.mutationCb;
        this.mirror = options.mirror;
        if (options.recordCanvas === true)
            this.initCanvasMutationObserver(options.win, options.blockClass);
    }
    CanvasManager.prototype.reset = function () {
        this.pendingCanvasMutations.clear();
        this.resetObservers && this.resetObservers();
    };
    CanvasManager.prototype.freeze = function () {
        this.frozen = true;
    };
    CanvasManager.prototype.unfreeze = function () {
        this.frozen = false;
    };
    CanvasManager.prototype.lock = function () {
        this.locked = true;
    };
    CanvasManager.prototype.unlock = function () {
        this.locked = false;
    };
    CanvasManager.prototype.initCanvasMutationObserver = function (win, blockClass) {
        this.startRAFTimestamping();
        this.startPendingCanvasMutationFlusher();
        var canvasContextReset = canvas.default(win, blockClass);
        var canvas2DReset = _2d.default(this.processMutation.bind(this), win, blockClass, this.mirror);
        var canvasWebGL1and2Reset = webgl.default(this.processMutation.bind(this), win, blockClass, this.mirror);
        this.resetObservers = function () {
            canvasContextReset();
            canvas2DReset();
            canvasWebGL1and2Reset();
        };
    };
    CanvasManager.prototype.startPendingCanvasMutationFlusher = function () {
        var _this = this;
        requestAnimationFrame(function () { return _this.flushPendingCanvasMutations(); });
    };
    CanvasManager.prototype.startRAFTimestamping = function () {
        var _this = this;
        var setLatestRAFTimestamp = function (timestamp) {
            _this.rafStamps.latestId = timestamp;
            requestAnimationFrame(setLatestRAFTimestamp);
        };
        requestAnimationFrame(setLatestRAFTimestamp);
    };
    CanvasManager.prototype.flushPendingCanvasMutations = function () {
        var _this = this;
        this.pendingCanvasMutations.forEach(function (values, canvas) {
            var id = _this.mirror.getId(canvas);
            _this.flushPendingCanvasMutationFor(canvas, id);
        });
        requestAnimationFrame(function () { return _this.flushPendingCanvasMutations(); });
    };
    CanvasManager.prototype.flushPendingCanvasMutationFor = function (canvas, id) {
        if (this.frozen || this.locked) {
            return;
        }
        var valuesWithType = this.pendingCanvasMutations.get(canvas);
        if (!valuesWithType || id === -1)
            return;
        var values = valuesWithType.map(function (value) {
            value.type; var rest = tslib_es6.__rest(value, ["type"]);
            return rest;
        });
        var type = valuesWithType[0].type;
        this.mutationCb({ id: id, type: type, commands: values });
        this.pendingCanvasMutations.delete(canvas);
    };
    return CanvasManager;
}());

exports.CanvasManager = CanvasManager;


},{"../../../../ext/tslib/tslib.es6.js":55,"./2d.js":69,"./canvas.js":71,"./webgl.js":73}],71:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');
const utils = require('../../../utils.js');

function initCanvasContextObserver(win, blockClass) {
    var handlers = [];
    try {
        var restoreHandler = utils.patch(win.HTMLCanvasElement.prototype, 'getContext', function (original) {
            return function (contextType) {
                var args = [];
                for (var _i = 1; _i < arguments.length; _i++) {
                    args[_i - 1] = arguments[_i];
                }
                if (!utils.isBlocked(this, blockClass)) {
                    if (!('__context' in this))
                        this.__context = contextType;
                }
                return original.apply(this, tslib_es6.__spreadArray([contextType], tslib_es6.__read(args), false));
            };
        });
        handlers.push(restoreHandler);
    }
    catch (_a) {
        console.error('failed to patch HTMLCanvasElement.prototype.getContext');
    }
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}

exports.default = initCanvasContextObserver;


},{"../../../../ext/tslib/tslib.es6.js":55,"../../../utils.js":85}],72:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');
const base64Arraybuffer_es5 = require('../../../../../../ext/base64-arraybuffer/dist/base64-arraybuffer.es5.js');

var webGLVarMap = new Map();
function variableListFor(ctx, ctor) {
    var contextMap = webGLVarMap.get(ctx);
    if (!contextMap) {
        contextMap = new Map();
        webGLVarMap.set(ctx, contextMap);
    }
    if (!contextMap.has(ctor)) {
        contextMap.set(ctor, []);
    }
    return contextMap.get(ctor);
}
var saveWebGLVar = function (value, win, ctx) {
    if (!value ||
        !(isInstanceOfWebGLObject(value, win) || typeof value === 'object'))
        return;
    var name = value.constructor.name;
    var list = variableListFor(ctx, name);
    var index = list.indexOf(value);
    if (index === -1) {
        index = list.length;
        list.push(value);
    }
    return index;
};
function serializeArg(value, win, ctx) {
    if (value instanceof Array) {
        return value.map(function (arg) { return serializeArg(arg, win, ctx); });
    }
    else if (value === null) {
        return value;
    }
    else if (value instanceof Float32Array ||
        value instanceof Float64Array ||
        value instanceof Int32Array ||
        value instanceof Uint32Array ||
        value instanceof Uint8Array ||
        value instanceof Uint16Array ||
        value instanceof Int16Array ||
        value instanceof Int8Array ||
        value instanceof Uint8ClampedArray) {
        var name_1 = value.constructor.name;
        return {
            rr_type: name_1,
            args: [Object.values(value)],
        };
    }
    else if (value instanceof ArrayBuffer) {
        var name_2 = value.constructor.name;
        var base64 = base64Arraybuffer_es5.encode(value);
        return {
            rr_type: name_2,
            base64: base64,
        };
    }
    else if (value instanceof DataView) {
        var name_3 = value.constructor.name;
        return {
            rr_type: name_3,
            args: [
                serializeArg(value.buffer, win, ctx),
                value.byteOffset,
                value.byteLength,
            ],
        };
    }
    else if (value instanceof HTMLImageElement) {
        var name_4 = value.constructor.name;
        var src = value.src;
        return {
            rr_type: name_4,
            src: src,
        };
    }
    else if (value instanceof ImageData) {
        var name_5 = value.constructor.name;
        return {
            rr_type: name_5,
            args: [serializeArg(value.data, win, ctx), value.width, value.height],
        };
    }
    else if (isInstanceOfWebGLObject(value, win) || typeof value === 'object') {
        var name_6 = value.constructor.name;
        var index = saveWebGLVar(value, win, ctx);
        return {
            rr_type: name_6,
            index: index,
        };
    }
    return value;
}
var serializeArgs = function (args, win, ctx) {
    return tslib_es6.__spreadArray([], tslib_es6.__read(args), false).map(function (arg) { return serializeArg(arg, win, ctx); });
};
var isInstanceOfWebGLObject = function (value, win) {
    var webGLConstructorNames = [
        'WebGLActiveInfo',
        'WebGLBuffer',
        'WebGLFramebuffer',
        'WebGLProgram',
        'WebGLRenderbuffer',
        'WebGLShader',
        'WebGLShaderPrecisionFormat',
        'WebGLTexture',
        'WebGLUniformLocation',
        'WebGLVertexArrayObject',
        'WebGLVertexArrayObjectOES',
    ];
    var supportedWebGLConstructorNames = webGLConstructorNames.filter(function (name) { return typeof win[name] === 'function'; });
    return Boolean(supportedWebGLConstructorNames.find(function (name) { return value instanceof win[name]; }));
};

exports.isInstanceOfWebGLObject = isInstanceOfWebGLObject;
exports.saveWebGLVar = saveWebGLVar;
exports.serializeArg = serializeArg;
exports.serializeArgs = serializeArgs;
exports.variableListFor = variableListFor;


},{"../../../../../../ext/base64-arraybuffer/dist/base64-arraybuffer.es5.js":51,"../../../../ext/tslib/tslib.es6.js":55}],73:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../../ext/tslib/tslib.es6.js');
const types = require('../../../types.js');
const utils = require('../../../utils.js');
const serializeArgs = require('./serialize-args.js');

function patchGLPrototype(prototype, type, cb, blockClass, mirror, win) {
    var e_1, _a;
    var handlers = [];
    var props = Object.getOwnPropertyNames(prototype);
    var _loop_1 = function (prop) {
        try {
            if (typeof prototype[prop] !== 'function') {
                return "continue";
            }
            var restoreHandler = utils.patch(prototype, prop, function (original) {
                return function () {
                    var args = [];
                    for (var _i = 0; _i < arguments.length; _i++) {
                        args[_i] = arguments[_i];
                    }
                    var result = original.apply(this, args);
                    serializeArgs.saveWebGLVar(result, win, prototype);
                    if (!utils.isBlocked(this.canvas, blockClass)) {
                        var id = mirror.getId(this.canvas);
                        var recordArgs = serializeArgs.serializeArgs(tslib_es6.__spreadArray([], tslib_es6.__read(args), false), win, prototype);
                        var mutation = {
                            type: type,
                            property: prop,
                            args: recordArgs,
                        };
                        cb(this.canvas, mutation);
                    }
                    return result;
                };
            });
            handlers.push(restoreHandler);
        }
        catch (_b) {
            var hookHandler = utils.hookSetter(prototype, prop, {
                set: function (v) {
                    cb(this.canvas, {
                        type: type,
                        property: prop,
                        args: [v],
                        setter: true,
                    });
                },
            });
            handlers.push(hookHandler);
        }
    };
    try {
        for (var props_1 = tslib_es6.__values(props), props_1_1 = props_1.next(); !props_1_1.done; props_1_1 = props_1.next()) {
            var prop = props_1_1.value;
            _loop_1(prop);
        }
    }
    catch (e_1_1) { e_1 = { error: e_1_1 }; }
    finally {
        try {
            if (props_1_1 && !props_1_1.done && (_a = props_1.return)) _a.call(props_1);
        }
        finally { if (e_1) throw e_1.error; }
    }
    return handlers;
}
function initCanvasWebGLMutationObserver(cb, win, blockClass, mirror) {
    var handlers = [];
    handlers.push.apply(handlers, tslib_es6.__spreadArray([], tslib_es6.__read(patchGLPrototype(win.WebGLRenderingContext.prototype, types.CanvasContext.WebGL, cb, blockClass, mirror, win)), false));
    if (typeof win.WebGL2RenderingContext !== 'undefined') {
        handlers.push.apply(handlers, tslib_es6.__spreadArray([], tslib_es6.__read(patchGLPrototype(win.WebGL2RenderingContext.prototype, types.CanvasContext.WebGL2, cb, blockClass, mirror, win)), false));
    }
    return function () {
        handlers.forEach(function (h) { return h(); });
    };
}

exports.default = initCanvasWebGLMutationObserver;


},{"../../../../ext/tslib/tslib.es6.js":55,"../../../types.js":84,"../../../utils.js":85,"./serialize-args.js":72}],74:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');
const observer = require('./observer.js');
const utils = require('../utils.js');

var ShadowDomManager = (function () {
    function ShadowDomManager(options) {
        this.restorePatches = [];
        this.mutationCb = options.mutationCb;
        this.scrollCb = options.scrollCb;
        this.bypassOptions = options.bypassOptions;
        this.mirror = options.mirror;
        var manager = this;
        this.restorePatches.push(utils.patch(HTMLElement.prototype, 'attachShadow', function (original) {
            return function () {
                var shadowRoot = original.apply(this, arguments);
                if (this.shadowRoot)
                    manager.addShadowRoot(this.shadowRoot, this.ownerDocument);
                return shadowRoot;
            };
        }));
    }
    ShadowDomManager.prototype.addShadowRoot = function (shadowRoot, doc) {
        observer.initMutationObserver(tslib_es6.__assign(tslib_es6.__assign({}, this.bypassOptions), { doc: doc, mutationCb: this.mutationCb, mirror: this.mirror, shadowDomManager: this }), shadowRoot);
        observer.initScrollObserver(tslib_es6.__assign(tslib_es6.__assign({}, this.bypassOptions), { scrollCb: this.scrollCb, doc: shadowRoot, mirror: this.mirror }));
    };
    ShadowDomManager.prototype.observeAttachShadow = function (iframeElement) {
        if (iframeElement.contentWindow) {
            var manager_1 = this;
            this.restorePatches.push(utils.patch(iframeElement.contentWindow.HTMLElement.prototype, 'attachShadow', function (original) {
                return function () {
                    var shadowRoot = original.apply(this, arguments);
                    if (this.shadowRoot)
                        manager_1.addShadowRoot(this.shadowRoot, iframeElement.contentDocument);
                    return shadowRoot;
                };
            }));
        }
    };
    ShadowDomManager.prototype.reset = function () {
        this.restorePatches.forEach(function (restorePatch) { return restorePatch(); });
    };
    return ShadowDomManager;
}());

exports.ShadowDomManager = ShadowDomManager;


},{"../../ext/tslib/tslib.es6.js":55,"../utils.js":85,"./observer.js":68}],75:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

function canvasMutation(_a) {
    var event = _a.event, mutation = _a.mutation, target = _a.target, imageMap = _a.imageMap, errorHandler = _a.errorHandler;
    try {
        var ctx = target.getContext('2d');
        if (mutation.setter) {
            ctx[mutation.property] = mutation.args[0];
            return;
        }
        var original = ctx[mutation.property];
        if (mutation.property === 'drawImage' &&
            typeof mutation.args[0] === 'string') {
            var image = imageMap.get(event);
            mutation.args[0] = image;
            original.apply(ctx, mutation.args);
        }
        else {
            original.apply(ctx, mutation.args);
        }
    }
    catch (error) {
        errorHandler(mutation, error);
    }
}

exports.default = canvasMutation;


},{}],76:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const types = require('../../types.js');
const webgl = require('./webgl.js');
const _2d = require('./2d.js');

function canvasMutation(_a) {
    var event = _a.event, mutation = _a.mutation, target = _a.target, imageMap = _a.imageMap, errorHandler = _a.errorHandler;
    try {
        var mutations = 'commands' in mutation ? mutation.commands : [mutation];
        if ([types.CanvasContext.WebGL, types.CanvasContext.WebGL2].includes(mutation.type)) {
            return mutations.forEach(function (command) {
                webgl.default({
                    mutation: command,
                    type: mutation.type,
                    target: target,
                    imageMap: imageMap,
                    errorHandler: errorHandler,
                });
            });
        }
        return mutations.forEach(function (command) {
            _2d.default({
                event: event,
                mutation: command,
                target: target,
                imageMap: imageMap,
                errorHandler: errorHandler,
            });
        });
    }
    catch (error) {
        errorHandler(mutation, error);
    }
}

exports.default = canvasMutation;


},{"../../types.js":84,"./2d.js":75,"./webgl.js":77}],77:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../../ext/tslib/tslib.es6.js');
const base64Arraybuffer_es5 = require('../../../../../ext/base64-arraybuffer/dist/base64-arraybuffer.es5.js');
const types = require('../../types.js');

var webGLVarMap = new Map();
function variableListFor(ctx, ctor) {
    var contextMap = webGLVarMap.get(ctx);
    if (!contextMap) {
        contextMap = new Map();
        webGLVarMap.set(ctx, contextMap);
    }
    if (!contextMap.has(ctor)) {
        contextMap.set(ctor, []);
    }
    return contextMap.get(ctor);
}
function getContext(target, type) {
    try {
        if (type === types.CanvasContext.WebGL) {
            return (target.getContext('webgl') || target.getContext('experimental-webgl'));
        }
        return target.getContext('webgl2');
    }
    catch (e) {
        return null;
    }
}
var WebGLVariableConstructorsNames = [
    'WebGLActiveInfo',
    'WebGLBuffer',
    'WebGLFramebuffer',
    'WebGLProgram',
    'WebGLRenderbuffer',
    'WebGLShader',
    'WebGLShaderPrecisionFormat',
    'WebGLTexture',
    'WebGLUniformLocation',
    'WebGLVertexArrayObject',
];
function saveToWebGLVarMap(ctx, result) {
    if (!(result === null || result === void 0 ? void 0 : result.constructor))
        return;
    var name = result.constructor.name;
    if (!WebGLVariableConstructorsNames.includes(name))
        return;
    var variables = variableListFor(ctx, name);
    if (!variables.includes(result))
        variables.push(result);
}
function deserializeArg(imageMap, ctx) {
    return function (arg) {
        if (arg && typeof arg === 'object' && 'rr_type' in arg) {
            if ('index' in arg) {
                var name_1 = arg.rr_type, index = arg.index;
                return variableListFor(ctx, name_1)[index];
            }
            else if ('args' in arg) {
                var name_2 = arg.rr_type, args = arg.args;
                var ctor = window[name_2];
                return new (ctor.bind.apply(ctor, tslib_es6.__spreadArray([void 0], tslib_es6.__read(args.map(deserializeArg(imageMap, ctx))), false)))();
            }
            else if ('base64' in arg) {
                return base64Arraybuffer_es5.decode(arg.base64);
            }
            else if ('src' in arg) {
                var image = imageMap.get(arg.src);
                if (image) {
                    return image;
                }
                else {
                    var image_1 = new Image();
                    image_1.src = arg.src;
                    imageMap.set(arg.src, image_1);
                    return image_1;
                }
            }
        }
        else if (Array.isArray(arg)) {
            return arg.map(deserializeArg(imageMap, ctx));
        }
        return arg;
    };
}
function webglMutation(_a) {
    var mutation = _a.mutation, target = _a.target, type = _a.type, imageMap = _a.imageMap, errorHandler = _a.errorHandler;
    try {
        var ctx = getContext(target, type);
        if (!ctx)
            return;
        if (mutation.setter) {
            ctx[mutation.property] = mutation.args[0];
            return;
        }
        var original = ctx[mutation.property];
        var args = mutation.args.map(deserializeArg(imageMap, ctx));
        var result = original.apply(ctx, args);
        saveToWebGLVarMap(ctx, result);
        var debugMode = false;
        if (debugMode) {
            if (mutation.property === 'compileShader') {
                if (!ctx.getShaderParameter(args[0], ctx.COMPILE_STATUS))
                    console.warn('something went wrong in replay', ctx.getShaderInfoLog(args[0]));
            }
            else if (mutation.property === 'linkProgram') {
                ctx.validateProgram(args[0]);
                if (!ctx.getProgramParameter(args[0], ctx.LINK_STATUS))
                    console.warn('something went wrong in replay', ctx.getProgramInfoLog(args[0]));
            }
            var webglError = ctx.getError();
            if (webglError !== ctx.NO_ERROR) {
                console.warn.apply(console, tslib_es6.__spreadArray(['WEBGL ERROR',
                    webglError,
                    'on command:',
                    mutation.property], tslib_es6.__read(args), false));
            }
        }
    }
    catch (error) {
        errorHandler(mutation, error);
    }
}

exports.default = webglMutation;
exports.deserializeArg = deserializeArg;
exports.variableListFor = variableListFor;


},{"../../../../../ext/base64-arraybuffer/dist/base64-arraybuffer.es5.js":51,"../../../ext/tslib/tslib.es6.js":55,"../../types.js":84}],78:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');
const rrwebSnapshot = require('../../../rrweb-snapshot/es/rrweb-snapshot.js');
const mitt_es = require('../../../../ext/mitt/dist/mitt.es.js');
const smoothscroll = require('./smoothscroll.js');
const timer = require('./timer.js');
const machine = require('./machine.js');
const types = require('../types.js');
const utils = require('../utils.js');
const injectStyle = require('./styles/inject-style.js');
const virtualStyles = require('./virtual-styles.js');
const index = require('./canvas/index.js');

var SKIP_TIME_THRESHOLD = 10 * 1000;
var SKIP_TIME_INTERVAL = 5 * 1000;
var mitt = mitt_es.default || mitt_es;
var REPLAY_CONSOLE_PREFIX = '[replayer]';
var defaultMouseTailConfig = {
    duration: 500,
    lineCap: 'round',
    lineWidth: 3,
    strokeStyle: 'red',
};
function indicatesTouchDevice(e) {
    return (e.type == types.EventType.IncrementalSnapshot &&
        (e.data.source == types.IncrementalSource.TouchMove ||
            (e.data.source == types.IncrementalSource.MouseInteraction &&
                e.data.type == types.MouseInteractions.TouchStart)));
}
var Replayer = (function () {
    function Replayer(events, config) {
        var _this = this;
        this.mouseTail = null;
        this.tailPositions = [];
        this.emitter = mitt();
        this.legacy_missingNodeRetryMap = {};
        this.cache = rrwebSnapshot.createCache();
        this.imageMap = new Map();
        this.mirror = utils.createMirror();
        this.firstFullSnapshot = null;
        this.newDocumentQueue = [];
        this.mousePos = null;
        this.touchActive = null;
        if (!(config === null || config === void 0 ? void 0 : config.liveMode) && events.length < 2) {
            throw new Error('Replayer need at least 2 events.');
        }
        var defaultConfig = {
            speed: 1,
            maxSpeed: 360,
            root: document.body,
            loadTimeout: 0,
            skipInactive: false,
            showWarning: true,
            showDebug: false,
            blockClass: 'rr-block',
            liveMode: false,
            insertStyleRules: [],
            triggerFocus: true,
            UNSAFE_replayCanvas: false,
            pauseAnimation: true,
            mouseTail: defaultMouseTailConfig,
        };
        this.config = Object.assign({}, defaultConfig, config);
        this.handleResize = this.handleResize.bind(this);
        this.getCastFn = this.getCastFn.bind(this);
        this.applyEventsSynchronously = this.applyEventsSynchronously.bind(this);
        this.emitter.on(types.ReplayerEvents.Resize, this.handleResize);
        this.setupDom();
        this.treeIndex = new utils.TreeIndex();
        this.fragmentParentMap = new Map();
        this.elementStateMap = new Map();
        this.virtualStyleRulesMap = new Map();
        this.emitter.on(types.ReplayerEvents.Flush, function () {
            var e_1, _a, e_2, _b, e_3, _c, e_4, _d;
            var _e = _this.treeIndex.flush(), scrollMap = _e.scrollMap, inputMap = _e.inputMap, mutationData = _e.mutationData;
            _this.fragmentParentMap.forEach(function (parent, frag) {
                return _this.restoreRealParent(frag, parent);
            });
            try {
                for (var _f = tslib_es6.__values(mutationData.texts), _g = _f.next(); !_g.done; _g = _f.next()) {
                    var d = _g.value;
                    _this.applyText(d, mutationData);
                }
            }
            catch (e_1_1) { e_1 = { error: e_1_1 }; }
            finally {
                try {
                    if (_g && !_g.done && (_a = _f.return)) _a.call(_f);
                }
                finally { if (e_1) throw e_1.error; }
            }
            try {
                for (var _h = tslib_es6.__values(_this.virtualStyleRulesMap.keys()), _j = _h.next(); !_j.done; _j = _h.next()) {
                    var node = _j.value;
                    _this.restoreNodeSheet(node);
                }
            }
            catch (e_2_1) { e_2 = { error: e_2_1 }; }
            finally {
                try {
                    if (_j && !_j.done && (_b = _h.return)) _b.call(_h);
                }
                finally { if (e_2) throw e_2.error; }
            }
            _this.fragmentParentMap.clear();
            _this.elementStateMap.clear();
            _this.virtualStyleRulesMap.clear();
            try {
                for (var _k = tslib_es6.__values(scrollMap.values()), _l = _k.next(); !_l.done; _l = _k.next()) {
                    var d = _l.value;
                    _this.applyScroll(d, true);
                }
            }
            catch (e_3_1) { e_3 = { error: e_3_1 }; }
            finally {
                try {
                    if (_l && !_l.done && (_c = _k.return)) _c.call(_k);
                }
                finally { if (e_3) throw e_3.error; }
            }
            try {
                for (var _m = tslib_es6.__values(inputMap.values()), _o = _m.next(); !_o.done; _o = _m.next()) {
                    var d = _o.value;
                    _this.applyInput(d);
                }
            }
            catch (e_4_1) { e_4 = { error: e_4_1 }; }
            finally {
                try {
                    if (_o && !_o.done && (_d = _m.return)) _d.call(_m);
                }
                finally { if (e_4) throw e_4.error; }
            }
        });
        this.emitter.on(types.ReplayerEvents.PlayBack, function () {
            _this.firstFullSnapshot = null;
            _this.mirror.reset();
        });
        var timer$1 = new timer.Timer([], (config === null || config === void 0 ? void 0 : config.speed) || defaultConfig.speed);
        this.service = machine.createPlayerService({
            events: events
                .map(function (e) {
                if (config && config.unpackFn) {
                    return config.unpackFn(e);
                }
                return e;
            })
                .sort(function (a1, a2) { return a1.timestamp - a2.timestamp; }),
            timer: timer$1,
            timeOffset: 0,
            baselineTime: 0,
            lastPlayedEvent: null,
        }, {
            getCastFn: this.getCastFn,
            applyEventsSynchronously: this.applyEventsSynchronously,
            emitter: this.emitter,
        });
        this.service.start();
        this.service.subscribe(function (state) {
            _this.emitter.emit(types.ReplayerEvents.StateChange, {
                player: state,
            });
        });
        this.speedService = machine.createSpeedService({
            normalSpeed: -1,
            timer: timer$1,
        });
        this.speedService.start();
        this.speedService.subscribe(function (state) {
            _this.emitter.emit(types.ReplayerEvents.StateChange, {
                speed: state,
            });
        });
        var firstMeta = this.service.state.context.events.find(function (e) { return e.type === types.EventType.Meta; });
        var firstFullsnapshot = this.service.state.context.events.find(function (e) { return e.type === types.EventType.FullSnapshot; });
        if (firstMeta) {
            var _a = firstMeta.data, width_1 = _a.width, height_1 = _a.height;
            setTimeout(function () {
                _this.emitter.emit(types.ReplayerEvents.Resize, {
                    width: width_1,
                    height: height_1,
                });
            }, 0);
        }
        if (firstFullsnapshot) {
            setTimeout(function () {
                if (_this.firstFullSnapshot) {
                    return;
                }
                _this.firstFullSnapshot = firstFullsnapshot;
                _this.rebuildFullSnapshot(firstFullsnapshot);
                _this.iframe.contentWindow.scrollTo(firstFullsnapshot.data.initialOffset);
            }, 1);
        }
        if (this.service.state.context.events.find(indicatesTouchDevice)) {
            this.mouse.classList.add('touch-device');
        }
    }
    Object.defineProperty(Replayer.prototype, "timer", {
        get: function () {
            return this.service.state.context.timer;
        },
        enumerable: false,
        configurable: true
    });
    Replayer.prototype.on = function (event, handler) {
        this.emitter.on(event, handler);
        return this;
    };
    Replayer.prototype.off = function (event, handler) {
        this.emitter.off(event, handler);
        return this;
    };
    Replayer.prototype.setConfig = function (config) {
        var _this = this;
        Object.keys(config).forEach(function (key) {
            _this.config[key] = config[key];
        });
        if (!this.config.skipInactive) {
            this.backToNormal();
        }
        if (typeof config.speed !== 'undefined') {
            this.speedService.send({
                type: 'SET_SPEED',
                payload: {
                    speed: config.speed,
                },
            });
        }
        if (typeof config.mouseTail !== 'undefined') {
            if (config.mouseTail === false) {
                if (this.mouseTail) {
                    this.mouseTail.style.display = 'none';
                }
            }
            else {
                if (!this.mouseTail) {
                    this.mouseTail = document.createElement('canvas');
                    this.mouseTail.width = Number.parseFloat(this.iframe.width);
                    this.mouseTail.height = Number.parseFloat(this.iframe.height);
                    this.mouseTail.classList.add('replayer-mouse-tail');
                    this.wrapper.insertBefore(this.mouseTail, this.iframe);
                }
                this.mouseTail.style.display = 'inherit';
            }
        }
    };
    Replayer.prototype.getMetaData = function () {
        var firstEvent = this.service.state.context.events[0];
        var lastEvent = this.service.state.context.events[this.service.state.context.events.length - 1];
        return {
            startTime: firstEvent.timestamp,
            endTime: lastEvent.timestamp,
            totalTime: lastEvent.timestamp - firstEvent.timestamp,
        };
    };
    Replayer.prototype.getCurrentTime = function () {
        return this.timer.timeOffset + this.getTimeOffset();
    };
    Replayer.prototype.getTimeOffset = function () {
        var _a = this.service.state.context, baselineTime = _a.baselineTime, events = _a.events;
        return baselineTime - events[0].timestamp;
    };
    Replayer.prototype.getMirror = function () {
        return this.mirror;
    };
    Replayer.prototype.play = function (timeOffset) {
        var _a;
        if (timeOffset === void 0) { timeOffset = 0; }
        if (this.service.state.matches('paused')) {
            this.service.send({ type: 'PLAY', payload: { timeOffset: timeOffset } });
        }
        else {
            this.service.send({ type: 'PAUSE' });
            this.service.send({ type: 'PLAY', payload: { timeOffset: timeOffset } });
        }
        (_a = this.iframe.contentDocument) === null || _a === void 0 ? void 0 : _a.getElementsByTagName('html')[0].classList.remove('rrweb-paused');
        this.emitter.emit(types.ReplayerEvents.Start);
    };
    Replayer.prototype.pause = function (timeOffset) {
        var _a;
        if (timeOffset === undefined && this.service.state.matches('playing')) {
            this.service.send({ type: 'PAUSE' });
        }
        if (typeof timeOffset === 'number') {
            this.play(timeOffset);
            this.service.send({ type: 'PAUSE' });
        }
        (_a = this.iframe.contentDocument) === null || _a === void 0 ? void 0 : _a.getElementsByTagName('html')[0].classList.add('rrweb-paused');
        this.emitter.emit(types.ReplayerEvents.Pause);
    };
    Replayer.prototype.resume = function (timeOffset) {
        if (timeOffset === void 0) { timeOffset = 0; }
        console.warn("The 'resume' will be departed in 1.0. Please use 'play' method which has the same interface.");
        this.play(timeOffset);
        this.emitter.emit(types.ReplayerEvents.Resume);
    };
    Replayer.prototype.startLive = function (baselineTime) {
        this.service.send({ type: 'TO_LIVE', payload: { baselineTime: baselineTime } });
    };
    Replayer.prototype.addEvent = function (rawEvent) {
        var _this = this;
        var event = this.config.unpackFn
            ? this.config.unpackFn(rawEvent)
            : rawEvent;
        if (indicatesTouchDevice(event)) {
            this.mouse.classList.add('touch-device');
        }
        Promise.resolve().then(function () {
            return _this.service.send({ type: 'ADD_EVENT', payload: { event: event } });
        });
    };
    Replayer.prototype.enableInteract = function () {
        this.iframe.setAttribute('scrolling', 'auto');
        this.iframe.style.pointerEvents = 'auto';
    };
    Replayer.prototype.disableInteract = function () {
        this.iframe.setAttribute('scrolling', 'no');
        this.iframe.style.pointerEvents = 'none';
    };
    Replayer.prototype.resetCache = function () {
        this.cache = rrwebSnapshot.createCache();
    };
    Replayer.prototype.setupDom = function () {
        this.wrapper = document.createElement('div');
        this.wrapper.classList.add('replayer-wrapper');
        this.config.root.appendChild(this.wrapper);
        this.mouse = document.createElement('div');
        this.mouse.classList.add('replayer-mouse');
        this.wrapper.appendChild(this.mouse);
        if (this.config.mouseTail !== false) {
            this.mouseTail = document.createElement('canvas');
            this.mouseTail.classList.add('replayer-mouse-tail');
            this.mouseTail.style.display = 'inherit';
            this.wrapper.appendChild(this.mouseTail);
        }
        this.iframe = document.createElement('iframe');
        var attributes = ['allow-same-origin'];
        if (this.config.UNSAFE_replayCanvas) {
            attributes.push('allow-scripts');
        }
        this.iframe.style.display = 'none';
        this.iframe.setAttribute('sandbox', attributes.join(' '));
        this.disableInteract();
        this.wrapper.appendChild(this.iframe);
        if (this.iframe.contentWindow && this.iframe.contentDocument) {
            smoothscroll.polyfill(this.iframe.contentWindow, this.iframe.contentDocument);
            utils.polyfill(this.iframe.contentWindow);
        }
    };
    Replayer.prototype.handleResize = function (dimension) {
        var e_5, _a;
        this.iframe.style.display = 'inherit';
        try {
            for (var _b = tslib_es6.__values([this.mouseTail, this.iframe]), _c = _b.next(); !_c.done; _c = _b.next()) {
                var el = _c.value;
                if (!el) {
                    continue;
                }
                el.setAttribute('width', String(dimension.width));
                el.setAttribute('height', String(dimension.height));
            }
        }
        catch (e_5_1) { e_5 = { error: e_5_1 }; }
        finally {
            try {
                if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
            }
            finally { if (e_5) throw e_5.error; }
        }
    };
    Replayer.prototype.applyEventsSynchronously = function (events) {
        var e_6, _a;
        try {
            for (var events_1 = tslib_es6.__values(events), events_1_1 = events_1.next(); !events_1_1.done; events_1_1 = events_1.next()) {
                var event_1 = events_1_1.value;
                switch (event_1.type) {
                    case types.EventType.DomContentLoaded:
                    case types.EventType.Load:
                    case types.EventType.Custom:
                        continue;
                    case types.EventType.FullSnapshot:
                    case types.EventType.Meta:
                    case types.EventType.Plugin:
                        break;
                    case types.EventType.IncrementalSnapshot:
                        switch (event_1.data.source) {
                            case types.IncrementalSource.MediaInteraction:
                                continue;
                            default:
                                break;
                        }
                        break;
                    default:
                        break;
                }
                var castFn = this.getCastFn(event_1, true);
                castFn();
            }
        }
        catch (e_6_1) { e_6 = { error: e_6_1 }; }
        finally {
            try {
                if (events_1_1 && !events_1_1.done && (_a = events_1.return)) _a.call(events_1);
            }
            finally { if (e_6) throw e_6.error; }
        }
        if (this.mousePos) {
            this.moveAndHover(this.mousePos.x, this.mousePos.y, this.mousePos.id, true, this.mousePos.debugData);
        }
        this.mousePos = null;
        if (this.touchActive === true) {
            this.mouse.classList.add('touch-active');
        }
        else if (this.touchActive === false) {
            this.mouse.classList.remove('touch-active');
        }
        this.touchActive = null;
    };
    Replayer.prototype.getCastFn = function (event, isSync) {
        var _this = this;
        if (isSync === void 0) { isSync = false; }
        var castFn;
        switch (event.type) {
            case types.EventType.DomContentLoaded:
            case types.EventType.Load:
                break;
            case types.EventType.Custom:
                castFn = function () {
                    _this.emitter.emit(types.ReplayerEvents.CustomEvent, event);
                };
                break;
            case types.EventType.Meta:
                castFn = function () {
                    return _this.emitter.emit(types.ReplayerEvents.Resize, {
                        width: event.data.width,
                        height: event.data.height,
                    });
                };
                break;
            case types.EventType.FullSnapshot:
                castFn = function () {
                    if (_this.firstFullSnapshot) {
                        if (_this.firstFullSnapshot === event) {
                            _this.firstFullSnapshot = true;
                            return;
                        }
                    }
                    else {
                        _this.firstFullSnapshot = true;
                    }
                    _this.rebuildFullSnapshot(event, isSync);
                    _this.iframe.contentWindow.scrollTo(event.data.initialOffset);
                };
                break;
            case types.EventType.IncrementalSnapshot:
                castFn = function () {
                    var e_7, _a;
                    _this.applyIncremental(event, isSync);
                    if (isSync) {
                        return;
                    }
                    if (event === _this.nextUserInteractionEvent) {
                        _this.nextUserInteractionEvent = null;
                        _this.backToNormal();
                    }
                    if (_this.config.skipInactive && !_this.nextUserInteractionEvent) {
                        try {
                            for (var _b = tslib_es6.__values(_this.service.state.context.events), _c = _b.next(); !_c.done; _c = _b.next()) {
                                var _event = _c.value;
                                if (_event.timestamp <= event.timestamp) {
                                    continue;
                                }
                                if (_this.isUserInteraction(_event)) {
                                    if (_event.delay - event.delay >
                                        SKIP_TIME_THRESHOLD *
                                            _this.speedService.state.context.timer.speed) {
                                        _this.nextUserInteractionEvent = _event;
                                    }
                                    break;
                                }
                            }
                        }
                        catch (e_7_1) { e_7 = { error: e_7_1 }; }
                        finally {
                            try {
                                if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
                            }
                            finally { if (e_7) throw e_7.error; }
                        }
                        if (_this.nextUserInteractionEvent) {
                            var skipTime = _this.nextUserInteractionEvent.delay - event.delay;
                            var payload = {
                                speed: Math.min(Math.round(skipTime / SKIP_TIME_INTERVAL), _this.config.maxSpeed),
                            };
                            _this.speedService.send({ type: 'FAST_FORWARD', payload: payload });
                            _this.emitter.emit(types.ReplayerEvents.SkipStart, payload);
                        }
                    }
                };
                break;
        }
        var wrappedCastFn = function () {
            var e_8, _a;
            if (castFn) {
                castFn();
            }
            try {
                for (var _b = tslib_es6.__values(_this.config.plugins || []), _c = _b.next(); !_c.done; _c = _b.next()) {
                    var plugin = _c.value;
                    plugin.handler(event, isSync, { replayer: _this });
                }
            }
            catch (e_8_1) { e_8 = { error: e_8_1 }; }
            finally {
                try {
                    if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
                }
                finally { if (e_8) throw e_8.error; }
            }
            _this.service.send({ type: 'CAST_EVENT', payload: { event: event } });
            var last_index = _this.service.state.context.events.length - 1;
            if (event === _this.service.state.context.events[last_index]) {
                var finish_1 = function () {
                    if (last_index < _this.service.state.context.events.length - 1) {
                        return;
                    }
                    _this.backToNormal();
                    _this.service.send('END');
                    _this.emitter.emit(types.ReplayerEvents.Finish);
                };
                if (event.type === types.EventType.IncrementalSnapshot &&
                    event.data.source === types.IncrementalSource.MouseMove &&
                    event.data.positions.length) {
                    setTimeout(function () {
                        finish_1();
                    }, Math.max(0, -event.data.positions[0].timeOffset + 50));
                }
                else {
                    finish_1();
                }
            }
            _this.emitter.emit(types.ReplayerEvents.EventCast, event);
        };
        return wrappedCastFn;
    };
    Replayer.prototype.rebuildFullSnapshot = function (event, isSync) {
        var e_9, _a;
        var _this = this;
        if (isSync === void 0) { isSync = false; }
        if (!this.iframe.contentDocument) {
            return console.warn('Looks like your replayer has been destroyed.');
        }
        if (Object.keys(this.legacy_missingNodeRetryMap).length) {
            console.warn('Found unresolved missing node map', this.legacy_missingNodeRetryMap);
        }
        this.legacy_missingNodeRetryMap = {};
        var collected = [];
        this.mirror.map = rrwebSnapshot.rebuild(event.data.node, {
            doc: this.iframe.contentDocument,
            afterAppend: function (builtNode) {
                _this.collectIframeAndAttachDocument(collected, builtNode);
            },
            cache: this.cache,
        })[1];
        var _loop_1 = function (mutationInQueue, builtNode) {
            this_1.attachDocumentToIframe(mutationInQueue, builtNode);
            this_1.newDocumentQueue = this_1.newDocumentQueue.filter(function (m) { return m !== mutationInQueue; });
        };
        var this_1 = this;
        try {
            for (var collected_1 = tslib_es6.__values(collected), collected_1_1 = collected_1.next(); !collected_1_1.done; collected_1_1 = collected_1.next()) {
                var _b = collected_1_1.value, mutationInQueue = _b.mutationInQueue, builtNode = _b.builtNode;
                _loop_1(mutationInQueue, builtNode);
            }
        }
        catch (e_9_1) { e_9 = { error: e_9_1 }; }
        finally {
            try {
                if (collected_1_1 && !collected_1_1.done && (_a = collected_1.return)) _a.call(collected_1);
            }
            finally { if (e_9) throw e_9.error; }
        }
        var _c = this.iframe.contentDocument, documentElement = _c.documentElement, head = _c.head;
        this.insertStyleRules(documentElement, head);
        if (!this.service.state.matches('playing')) {
            this.iframe.contentDocument
                .getElementsByTagName('html')[0]
                .classList.add('rrweb-paused');
        }
        this.emitter.emit(types.ReplayerEvents.FullsnapshotRebuilded, event);
        if (!isSync) {
            this.waitForStylesheetLoad();
        }
        if (this.config.UNSAFE_replayCanvas) {
            this.preloadAllImages();
        }
    };
    Replayer.prototype.insertStyleRules = function (documentElement, head) {
        var styleEl = document.createElement('style');
        documentElement.insertBefore(styleEl, head);
        var injectStylesRules = injectStyle.default(this.config.blockClass).concat(this.config.insertStyleRules);
        if (this.config.pauseAnimation) {
            injectStylesRules.push('html.rrweb-paused *, html.rrweb-paused *:before, html.rrweb-paused *:after { animation-play-state: paused !important; }');
        }
        for (var idx = 0; idx < injectStylesRules.length; idx++) {
            styleEl.sheet.insertRule(injectStylesRules[idx], idx);
        }
    };
    Replayer.prototype.attachDocumentToIframe = function (mutation, iframeEl) {
        var e_10, _a;
        var _this = this;
        var collected = [];
        if (!iframeEl.contentDocument) {
            var parent_1 = iframeEl.parentNode;
            while (parent_1) {
                if (this.fragmentParentMap.has(parent_1)) {
                    var frag = parent_1;
                    var realParent = this.fragmentParentMap.get(frag);
                    this.restoreRealParent(frag, realParent);
                    break;
                }
                parent_1 = parent_1.parentNode;
            }
        }
        rrwebSnapshot.buildNodeWithSN(mutation.node, {
            doc: iframeEl.contentDocument,
            map: this.mirror.map,
            hackCss: true,
            skipChild: false,
            afterAppend: function (builtNode) {
                _this.collectIframeAndAttachDocument(collected, builtNode);
                if (builtNode.__sn.type === rrwebSnapshot.NodeType.Element &&
                    builtNode.__sn.tagName.toUpperCase() === 'HTML') {
                    var _a = iframeEl.contentDocument, documentElement = _a.documentElement, head = _a.head;
                    _this.insertStyleRules(documentElement, head);
                }
            },
            cache: this.cache,
        });
        var _loop_2 = function (mutationInQueue, builtNode) {
            this_2.attachDocumentToIframe(mutationInQueue, builtNode);
            this_2.newDocumentQueue = this_2.newDocumentQueue.filter(function (m) { return m !== mutationInQueue; });
        };
        var this_2 = this;
        try {
            for (var collected_2 = tslib_es6.__values(collected), collected_2_1 = collected_2.next(); !collected_2_1.done; collected_2_1 = collected_2.next()) {
                var _b = collected_2_1.value, mutationInQueue = _b.mutationInQueue, builtNode = _b.builtNode;
                _loop_2(mutationInQueue, builtNode);
            }
        }
        catch (e_10_1) { e_10 = { error: e_10_1 }; }
        finally {
            try {
                if (collected_2_1 && !collected_2_1.done && (_a = collected_2.return)) _a.call(collected_2);
            }
            finally { if (e_10) throw e_10.error; }
        }
    };
    Replayer.prototype.collectIframeAndAttachDocument = function (collected, builtNode) {
        if (utils.isIframeINode(builtNode)) {
            var mutationInQueue = this.newDocumentQueue.find(function (m) { return m.parentId === builtNode.__sn.id; });
            if (mutationInQueue) {
                collected.push({ mutationInQueue: mutationInQueue, builtNode: builtNode });
            }
        }
    };
    Replayer.prototype.waitForStylesheetLoad = function () {
        var _this = this;
        var _a;
        var head = (_a = this.iframe.contentDocument) === null || _a === void 0 ? void 0 : _a.head;
        if (head) {
            var unloadSheets_1 = new Set();
            var timer_1;
            var beforeLoadState_1 = this.service.state;
            var stateHandler_1 = function () {
                beforeLoadState_1 = _this.service.state;
            };
            this.emitter.on(types.ReplayerEvents.Start, stateHandler_1);
            this.emitter.on(types.ReplayerEvents.Pause, stateHandler_1);
            var unsubscribe_1 = function () {
                _this.emitter.off(types.ReplayerEvents.Start, stateHandler_1);
                _this.emitter.off(types.ReplayerEvents.Pause, stateHandler_1);
            };
            head
                .querySelectorAll('link[rel="stylesheet"]')
                .forEach(function (css) {
                if (!css.sheet) {
                    unloadSheets_1.add(css);
                    css.addEventListener('load', function () {
                        unloadSheets_1.delete(css);
                        if (unloadSheets_1.size === 0 && timer_1 !== -1) {
                            if (beforeLoadState_1.matches('playing')) {
                                _this.play(_this.getCurrentTime());
                            }
                            _this.emitter.emit(types.ReplayerEvents.LoadStylesheetEnd);
                            if (timer_1) {
                                clearTimeout(timer_1);
                            }
                            unsubscribe_1();
                        }
                    });
                }
            });
            if (unloadSheets_1.size > 0) {
                this.service.send({ type: 'PAUSE' });
                this.emitter.emit(types.ReplayerEvents.LoadStylesheetStart);
                timer_1 = setTimeout(function () {
                    if (beforeLoadState_1.matches('playing')) {
                        _this.play(_this.getCurrentTime());
                    }
                    timer_1 = -1;
                    unsubscribe_1();
                }, this.config.loadTimeout);
            }
        }
    };
    Replayer.prototype.hasImageArg = function (args) {
        var e_11, _a;
        try {
            for (var args_1 = tslib_es6.__values(args), args_1_1 = args_1.next(); !args_1_1.done; args_1_1 = args_1.next()) {
                var arg = args_1_1.value;
                if (!arg || typeof arg !== 'object') {
                }
                else if ('rr_type' in arg && 'args' in arg) {
                    if (this.hasImageArg(arg.args))
                        return true;
                }
                else if ('rr_type' in arg && arg.rr_type === 'HTMLImageElement') {
                    return true;
                }
                else if (arg instanceof Array) {
                    if (this.hasImageArg(arg))
                        return true;
                }
            }
        }
        catch (e_11_1) { e_11 = { error: e_11_1 }; }
        finally {
            try {
                if (args_1_1 && !args_1_1.done && (_a = args_1.return)) _a.call(args_1);
            }
            finally { if (e_11) throw e_11.error; }
        }
        return false;
    };
    Replayer.prototype.getImageArgs = function (args) {
        var e_12, _a;
        var images = [];
        try {
            for (var args_2 = tslib_es6.__values(args), args_2_1 = args_2.next(); !args_2_1.done; args_2_1 = args_2.next()) {
                var arg = args_2_1.value;
                if (!arg || typeof arg !== 'object') {
                }
                else if ('rr_type' in arg && 'args' in arg) {
                    images.push.apply(images, tslib_es6.__spreadArray([], tslib_es6.__read(this.getImageArgs(arg.args)), false));
                }
                else if ('rr_type' in arg && arg.rr_type === 'HTMLImageElement') {
                    images.push(arg.src);
                }
                else if (arg instanceof Array) {
                    images.push.apply(images, tslib_es6.__spreadArray([], tslib_es6.__read(this.getImageArgs(arg)), false));
                }
            }
        }
        catch (e_12_1) { e_12 = { error: e_12_1 }; }
        finally {
            try {
                if (args_2_1 && !args_2_1.done && (_a = args_2.return)) _a.call(args_2);
            }
            finally { if (e_12) throw e_12.error; }
        }
        return images;
    };
    Replayer.prototype.preloadAllImages = function () {
        var e_13, _a;
        var _this = this;
        this.service.state;
        var stateHandler = function () {
            _this.service.state;
        };
        this.emitter.on(types.ReplayerEvents.Start, stateHandler);
        this.emitter.on(types.ReplayerEvents.Pause, stateHandler);
        var _loop_3 = function (event_2) {
            if (event_2.type === types.EventType.IncrementalSnapshot &&
                event_2.data.source === types.IncrementalSource.CanvasMutation)
                if ('commands' in event_2.data) {
                    event_2.data.commands.forEach(function (c) { return _this.preloadImages(c, event_2); });
                }
                else {
                    this_3.preloadImages(event_2.data, event_2);
                }
        };
        var this_3 = this;
        try {
            for (var _b = tslib_es6.__values(this.service.state.context.events), _c = _b.next(); !_c.done; _c = _b.next()) {
                var event_2 = _c.value;
                _loop_3(event_2);
            }
        }
        catch (e_13_1) { e_13 = { error: e_13_1 }; }
        finally {
            try {
                if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
            }
            finally { if (e_13) throw e_13.error; }
        }
    };
    Replayer.prototype.preloadImages = function (data, event) {
        var _this = this;
        if (data.property === 'drawImage' &&
            typeof data.args[0] === 'string' &&
            !this.imageMap.has(event)) {
            var canvas = document.createElement('canvas');
            var ctx = canvas.getContext('2d');
            var imgd = ctx === null || ctx === void 0 ? void 0 : ctx.createImageData(canvas.width, canvas.height);
            imgd === null || imgd === void 0 ? void 0 : imgd.data;
            JSON.parse(data.args[0]);
            ctx === null || ctx === void 0 ? void 0 : ctx.putImageData(imgd, 0, 0);
        }
        else if (this.hasImageArg(data.args)) {
            this.getImageArgs(data.args).forEach(function (url) {
                var image = new Image();
                image.src = url;
                _this.imageMap.set(url, image);
            });
        }
    };
    Replayer.prototype.applyIncremental = function (e, isSync) {
        var _this = this;
        var _a, _b;
        var d = e.data;
        switch (d.source) {
            case types.IncrementalSource.Mutation: {
                if (isSync) {
                    d.adds.forEach(function (m) { return _this.treeIndex.add(m); });
                    d.texts.forEach(function (m) {
                        var target = _this.mirror.getNode(m.id);
                        var parent = target === null || target === void 0 ? void 0 : target.parentNode;
                        if (parent && _this.virtualStyleRulesMap.has(parent))
                            _this.virtualStyleRulesMap.delete(parent);
                        _this.treeIndex.text(m);
                    });
                    d.attributes.forEach(function (m) { return _this.treeIndex.attribute(m); });
                    d.removes.forEach(function (m) { return _this.treeIndex.remove(m, _this.mirror); });
                }
                try {
                    this.applyMutation(d, isSync);
                }
                catch (error) {
                    this.warn("Exception in mutation ".concat(error.message || error), d);
                }
                break;
            }
            case types.IncrementalSource.Drag:
            case types.IncrementalSource.TouchMove:
            case types.IncrementalSource.MouseMove:
                if (isSync) {
                    var lastPosition = d.positions[d.positions.length - 1];
                    this.mousePos = {
                        x: lastPosition.x,
                        y: lastPosition.y,
                        id: lastPosition.id,
                        debugData: d,
                    };
                }
                else {
                    d.positions.forEach(function (p) {
                        var action = {
                            doAction: function () {
                                _this.moveAndHover(p.x, p.y, p.id, isSync, d);
                            },
                            delay: p.timeOffset +
                                e.timestamp -
                                _this.service.state.context.baselineTime,
                        };
                        _this.timer.addAction(action);
                    });
                    this.timer.addAction({
                        doAction: function () { },
                        delay: e.delay - ((_a = d.positions[0]) === null || _a === void 0 ? void 0 : _a.timeOffset),
                    });
                }
                break;
            case types.IncrementalSource.MouseInteraction: {
                if (d.id === -1) {
                    break;
                }
                var event_3 = new Event(types.MouseInteractions[d.type].toLowerCase());
                var target = this.mirror.getNode(d.id);
                if (!target) {
                    return this.debugNodeNotFound(d, d.id);
                }
                this.emitter.emit(types.ReplayerEvents.MouseInteraction, {
                    type: d.type,
                    target: target,
                });
                var triggerFocus = this.config.triggerFocus;
                switch (d.type) {
                    case types.MouseInteractions.Blur:
                        if ('blur' in target) {
                            target.blur();
                        }
                        break;
                    case types.MouseInteractions.Focus:
                        if (triggerFocus && target.focus) {
                            target.focus({
                                preventScroll: true,
                            });
                        }
                        break;
                    case types.MouseInteractions.Click:
                    case types.MouseInteractions.TouchStart:
                    case types.MouseInteractions.TouchEnd:
                        if (isSync) {
                            if (d.type === types.MouseInteractions.TouchStart) {
                                this.touchActive = true;
                            }
                            else if (d.type === types.MouseInteractions.TouchEnd) {
                                this.touchActive = false;
                            }
                            this.mousePos = {
                                x: d.x,
                                y: d.y,
                                id: d.id,
                                debugData: d,
                            };
                        }
                        else {
                            if (d.type === types.MouseInteractions.TouchStart) {
                                this.tailPositions.length = 0;
                            }
                            this.moveAndHover(d.x, d.y, d.id, isSync, d);
                            if (d.type === types.MouseInteractions.Click) {
                                this.mouse.classList.remove('active');
                                void this.mouse.offsetWidth;
                                this.mouse.classList.add('active');
                            }
                            else if (d.type === types.MouseInteractions.TouchStart) {
                                void this.mouse.offsetWidth;
                                this.mouse.classList.add('touch-active');
                            }
                            else if (d.type === types.MouseInteractions.TouchEnd) {
                                this.mouse.classList.remove('touch-active');
                            }
                        }
                        break;
                    case types.MouseInteractions.TouchCancel:
                        if (isSync) {
                            this.touchActive = false;
                        }
                        else {
                            this.mouse.classList.remove('touch-active');
                        }
                        break;
                    default:
                        target.dispatchEvent(event_3);
                }
                break;
            }
            case types.IncrementalSource.Scroll: {
                if (d.id === -1) {
                    break;
                }
                if (isSync) {
                    this.treeIndex.scroll(d);
                    break;
                }
                this.applyScroll(d, false);
                break;
            }
            case types.IncrementalSource.ViewportResize:
                this.emitter.emit(types.ReplayerEvents.Resize, {
                    width: d.width,
                    height: d.height,
                });
                break;
            case types.IncrementalSource.Input: {
                if (d.id === -1) {
                    break;
                }
                if (isSync) {
                    this.treeIndex.input(d);
                    break;
                }
                this.applyInput(d);
                break;
            }
            case types.IncrementalSource.MediaInteraction: {
                var target = this.mirror.getNode(d.id);
                if (!target) {
                    return this.debugNodeNotFound(d, d.id);
                }
                var mediaEl = target;
                try {
                    if (d.currentTime) {
                        mediaEl.currentTime = d.currentTime;
                    }
                    if (d.volume) {
                        mediaEl.volume = d.volume;
                    }
                    if (d.muted) {
                        mediaEl.muted = d.muted;
                    }
                    if (d.type === 1) {
                        mediaEl.pause();
                    }
                    if (d.type === 0) {
                        mediaEl.play();
                    }
                }
                catch (error) {
                    if (this.config.showWarning) {
                        console.warn("Failed to replay media interactions: ".concat(error.message || error));
                    }
                }
                break;
            }
            case types.IncrementalSource.StyleSheetRule: {
                var target = this.mirror.getNode(d.id);
                if (!target) {
                    return this.debugNodeNotFound(d, d.id);
                }
                var styleEl = target;
                var parent_2 = target.parentNode;
                var usingVirtualParent_1 = this.fragmentParentMap.has(parent_2);
                var styleSheet_1 = usingVirtualParent_1 ? null : styleEl.sheet;
                var rules_1;
                if (!styleSheet_1) {
                    if (this.virtualStyleRulesMap.has(target)) {
                        rules_1 = this.virtualStyleRulesMap.get(target);
                    }
                    else {
                        rules_1 = [];
                        this.virtualStyleRulesMap.set(target, rules_1);
                    }
                }
                if (d.adds) {
                    d.adds.forEach(function (_a) {
                        var rule = _a.rule, nestedIndex = _a.index;
                        if (styleSheet_1) {
                            try {
                                if (Array.isArray(nestedIndex)) {
                                    var _b = virtualStyles.getPositionsAndIndex(nestedIndex), positions = _b.positions, index = _b.index;
                                    var nestedRule = virtualStyles.getNestedRule(styleSheet_1.cssRules, positions);
                                    nestedRule.insertRule(rule, index);
                                }
                                else {
                                    var index = nestedIndex === undefined
                                        ? undefined
                                        : Math.min(nestedIndex, styleSheet_1.cssRules.length);
                                    styleSheet_1.insertRule(rule, index);
                                }
                            }
                            catch (e) {
                            }
                        }
                        else {
                            rules_1 === null || rules_1 === void 0 ? void 0 : rules_1.push({
                                cssText: rule,
                                index: nestedIndex,
                                type: virtualStyles.StyleRuleType.Insert,
                            });
                        }
                    });
                }
                if (d.removes) {
                    d.removes.forEach(function (_a) {
                        var nestedIndex = _a.index;
                        if (usingVirtualParent_1) {
                            rules_1 === null || rules_1 === void 0 ? void 0 : rules_1.push({ index: nestedIndex, type: virtualStyles.StyleRuleType.Remove });
                        }
                        else {
                            try {
                                if (Array.isArray(nestedIndex)) {
                                    var _b = virtualStyles.getPositionsAndIndex(nestedIndex), positions = _b.positions, index = _b.index;
                                    var nestedRule = virtualStyles.getNestedRule(styleSheet_1.cssRules, positions);
                                    nestedRule.deleteRule(index || 0);
                                }
                                else {
                                    styleSheet_1 === null || styleSheet_1 === void 0 ? void 0 : styleSheet_1.deleteRule(nestedIndex);
                                }
                            }
                            catch (e) {
                            }
                        }
                    });
                }
                break;
            }
            case types.IncrementalSource.StyleDeclaration: {
                var target = this.mirror.getNode(d.id);
                if (!target) {
                    return this.debugNodeNotFound(d, d.id);
                }
                var styleEl = target;
                var parent_3 = target.parentNode;
                var usingVirtualParent = this.fragmentParentMap.has(parent_3);
                var styleSheet = usingVirtualParent ? null : styleEl.sheet;
                var rules = [];
                if (!styleSheet) {
                    if (this.virtualStyleRulesMap.has(target)) {
                        rules = this.virtualStyleRulesMap.get(target);
                    }
                    else {
                        rules = [];
                        this.virtualStyleRulesMap.set(target, rules);
                    }
                }
                if (d.set) {
                    if (styleSheet) {
                        var rule = virtualStyles.getNestedRule(styleSheet.rules, d.index);
                        rule.style.setProperty(d.set.property, d.set.value, d.set.priority);
                    }
                    else {
                        rules.push(tslib_es6.__assign({ type: virtualStyles.StyleRuleType.SetProperty, index: d.index }, d.set));
                    }
                }
                if (d.remove) {
                    if (styleSheet) {
                        var rule = virtualStyles.getNestedRule(styleSheet.rules, d.index);
                        rule.style.removeProperty(d.remove.property);
                    }
                    else {
                        rules.push(tslib_es6.__assign({ type: virtualStyles.StyleRuleType.RemoveProperty, index: d.index }, d.remove));
                    }
                }
                break;
            }
            case types.IncrementalSource.CanvasMutation: {
                if (!this.config.UNSAFE_replayCanvas) {
                    return;
                }
                var target = this.mirror.getNode(d.id);
                if (!target) {
                    return this.debugNodeNotFound(d, d.id);
                }
                index.default({
                    event: e,
                    mutation: d,
                    target: target,
                    imageMap: this.imageMap,
                    errorHandler: this.warnCanvasMutationFailed.bind(this),
                });
                break;
            }
            case types.IncrementalSource.Font: {
                try {
                    var fontFace = new FontFace(d.family, d.buffer ? new Uint8Array(JSON.parse(d.fontSource)) : d.fontSource, d.descriptors);
                    (_b = this.iframe.contentDocument) === null || _b === void 0 ? void 0 : _b.fonts.add(fontFace);
                }
                catch (error) {
                    if (this.config.showWarning) {
                        console.warn(error);
                    }
                }
                break;
            }
        }
    };
    Replayer.prototype.applyMutation = function (d, useVirtualParent) {
        var e_14, _a;
        var _this = this;
        d.removes.forEach(function (mutation) {
            var target = _this.mirror.getNode(mutation.id);
            if (!target) {
                if (d.removes.find(function (r) { return r.id === mutation.parentId; })) {
                    return;
                }
                return _this.warnNodeNotFound(d, mutation.id);
            }
            if (_this.virtualStyleRulesMap.has(target)) {
                _this.virtualStyleRulesMap.delete(target);
            }
            var parent = _this.mirror.getNode(mutation.parentId);
            if (!parent) {
                return _this.warnNodeNotFound(d, mutation.parentId);
            }
            if (mutation.isShadow && utils.hasShadowRoot(parent)) {
                parent = parent.shadowRoot;
            }
            _this.mirror.removeNodeFromMap(target);
            if (parent) {
                var realTarget = null;
                var realParent = '__sn' in parent ? _this.fragmentParentMap.get(parent) : undefined;
                if (realParent && realParent.contains(target)) {
                    parent = realParent;
                }
                else if (_this.fragmentParentMap.has(target)) {
                    realTarget = _this.fragmentParentMap.get(target);
                    _this.fragmentParentMap.delete(target);
                    target = realTarget;
                }
                try {
                    parent.removeChild(target);
                }
                catch (error) {
                    if (error instanceof DOMException) {
                        _this.warn('parent could not remove child in mutation', parent, realParent, target, realTarget, d);
                    }
                    else {
                        throw error;
                    }
                }
            }
        });
        var legacy_missingNodeMap = tslib_es6.__assign({}, this.legacy_missingNodeRetryMap);
        var queue = [];
        var nextNotInDOM = function (mutation) {
            var next = null;
            if (mutation.nextId) {
                next = _this.mirror.getNode(mutation.nextId);
            }
            if (mutation.nextId !== null &&
                mutation.nextId !== undefined &&
                mutation.nextId !== -1 &&
                !next) {
                return true;
            }
            return false;
        };
        var appendNode = function (mutation) {
            var e_15, _a;
            var _b, _c;
            if (!_this.iframe.contentDocument) {
                return console.warn('Looks like your replayer has been destroyed.');
            }
            var parent = _this.mirror.getNode(mutation.parentId);
            if (!parent) {
                if (mutation.node.type === rrwebSnapshot.NodeType.Document) {
                    return _this.newDocumentQueue.push(mutation);
                }
                return queue.push(mutation);
            }
            var parentInDocument = null;
            if (_this.iframe.contentDocument.contains) {
                parentInDocument = _this.iframe.contentDocument.contains(parent);
            }
            else if (_this.iframe.contentDocument.body.contains) {
                parentInDocument = _this.iframe.contentDocument.body.contains(parent);
            }
            var hasIframeChild = ((_c = (_b = parent).getElementsByTagName) === null || _c === void 0 ? void 0 : _c.call(_b, 'iframe').length) > 0;
            if (useVirtualParent &&
                parentInDocument &&
                !utils.isIframeINode(parent) &&
                !hasIframeChild) {
                var virtualParent = document.createDocumentFragment();
                _this.mirror.map[mutation.parentId] = virtualParent;
                _this.fragmentParentMap.set(virtualParent, parent);
                _this.storeState(parent);
                while (parent.firstChild) {
                    virtualParent.appendChild(parent.firstChild);
                }
                parent = virtualParent;
            }
            if (mutation.node.isShadow) {
                if (!utils.hasShadowRoot(parent)) {
                    parent.attachShadow({ mode: 'open' });
                    parent = parent.shadowRoot;
                }
                else
                    parent = parent.shadowRoot;
            }
            var previous = null;
            var next = null;
            if (mutation.previousId) {
                previous = _this.mirror.getNode(mutation.previousId);
            }
            if (mutation.nextId) {
                next = _this.mirror.getNode(mutation.nextId);
            }
            if (nextNotInDOM(mutation)) {
                return queue.push(mutation);
            }
            if (mutation.node.rootId && !_this.mirror.getNode(mutation.node.rootId)) {
                return;
            }
            var targetDoc = mutation.node.rootId
                ? _this.mirror.getNode(mutation.node.rootId)
                : _this.iframe.contentDocument;
            if (utils.isIframeINode(parent)) {
                _this.attachDocumentToIframe(mutation, parent);
                return;
            }
            var target = rrwebSnapshot.buildNodeWithSN(mutation.node, {
                doc: targetDoc,
                map: _this.mirror.map,
                skipChild: true,
                hackCss: true,
                cache: _this.cache,
            });
            if (mutation.previousId === -1 || mutation.nextId === -1) {
                legacy_missingNodeMap[mutation.node.id] = {
                    node: target,
                    mutation: mutation,
                };
                return;
            }
            if ('__sn' in parent &&
                parent.__sn.type === rrwebSnapshot.NodeType.Element &&
                parent.__sn.tagName === 'textarea' &&
                mutation.node.type === rrwebSnapshot.NodeType.Text) {
                try {
                    for (var _d = tslib_es6.__values(Array.from(parent.childNodes)), _e = _d.next(); !_e.done; _e = _d.next()) {
                        var c = _e.value;
                        if (c.nodeType === parent.TEXT_NODE) {
                            parent.removeChild(c);
                        }
                    }
                }
                catch (e_15_1) { e_15 = { error: e_15_1 }; }
                finally {
                    try {
                        if (_e && !_e.done && (_a = _d.return)) _a.call(_d);
                    }
                    finally { if (e_15) throw e_15.error; }
                }
            }
            if (previous && previous.nextSibling && previous.nextSibling.parentNode) {
                parent.insertBefore(target, previous.nextSibling);
            }
            else if (next && next.parentNode) {
                parent.contains(next)
                    ? parent.insertBefore(target, next)
                    : parent.insertBefore(target, null);
            }
            else {
                if (parent === targetDoc) {
                    while (targetDoc.firstChild) {
                        targetDoc.removeChild(targetDoc.firstChild);
                    }
                }
                parent.appendChild(target);
            }
            if (utils.isIframeINode(target)) {
                var mutationInQueue_1 = _this.newDocumentQueue.find(function (m) { return m.parentId === target.__sn.id; });
                if (mutationInQueue_1) {
                    _this.attachDocumentToIframe(mutationInQueue_1, target);
                    _this.newDocumentQueue = _this.newDocumentQueue.filter(function (m) { return m !== mutationInQueue_1; });
                }
            }
            if (mutation.previousId || mutation.nextId) {
                _this.legacy_resolveMissingNode(legacy_missingNodeMap, parent, target, mutation);
            }
        };
        d.adds.forEach(function (mutation) {
            appendNode(mutation);
        });
        var startTime = Date.now();
        while (queue.length) {
            var resolveTrees = utils.queueToResolveTrees(queue);
            queue.length = 0;
            if (Date.now() - startTime > 500) {
                this.warn('Timeout in the loop, please check the resolve tree data:', resolveTrees);
                break;
            }
            try {
                for (var resolveTrees_1 = (e_14 = void 0, tslib_es6.__values(resolveTrees)), resolveTrees_1_1 = resolveTrees_1.next(); !resolveTrees_1_1.done; resolveTrees_1_1 = resolveTrees_1.next()) {
                    var tree = resolveTrees_1_1.value;
                    var parent_4 = this.mirror.getNode(tree.value.parentId);
                    if (!parent_4) {
                        this.debug('Drop resolve tree since there is no parent for the root node.', tree);
                    }
                    else {
                        utils.iterateResolveTree(tree, function (mutation) {
                            appendNode(mutation);
                        });
                    }
                }
            }
            catch (e_14_1) { e_14 = { error: e_14_1 }; }
            finally {
                try {
                    if (resolveTrees_1_1 && !resolveTrees_1_1.done && (_a = resolveTrees_1.return)) _a.call(resolveTrees_1);
                }
                finally { if (e_14) throw e_14.error; }
            }
        }
        if (Object.keys(legacy_missingNodeMap).length) {
            Object.assign(this.legacy_missingNodeRetryMap, legacy_missingNodeMap);
        }
        d.texts.forEach(function (mutation) {
            var target = _this.mirror.getNode(mutation.id);
            if (!target) {
                if (d.removes.find(function (r) { return r.id === mutation.id; })) {
                    return;
                }
                return _this.warnNodeNotFound(d, mutation.id);
            }
            if (_this.fragmentParentMap.has(target)) {
                target = _this.fragmentParentMap.get(target);
            }
            target.textContent = mutation.value;
        });
        d.attributes.forEach(function (mutation) {
            var target = _this.mirror.getNode(mutation.id);
            if (!target) {
                if (d.removes.find(function (r) { return r.id === mutation.id; })) {
                    return;
                }
                return _this.warnNodeNotFound(d, mutation.id);
            }
            if (_this.fragmentParentMap.has(target)) {
                target = _this.fragmentParentMap.get(target);
            }
            for (var attributeName in mutation.attributes) {
                if (typeof attributeName === 'string') {
                    var value = mutation.attributes[attributeName];
                    if (value === null) {
                        target.removeAttribute(attributeName);
                    }
                    else if (typeof value === 'string') {
                        try {
                            target.setAttribute(attributeName, value);
                        }
                        catch (error) {
                            if (_this.config.showWarning) {
                                console.warn('An error occurred may due to the checkout feature.', error);
                            }
                        }
                    }
                    else if (attributeName === 'style') {
                        var styleValues = value;
                        var targetEl = target;
                        for (var s in styleValues) {
                            if (styleValues[s] === false) {
                                targetEl.style.removeProperty(s);
                            }
                            else if (styleValues[s] instanceof Array) {
                                var svp = styleValues[s];
                                targetEl.style.setProperty(s, svp[0], svp[1]);
                            }
                            else {
                                var svs = styleValues[s];
                                targetEl.style.setProperty(s, svs);
                            }
                        }
                    }
                }
            }
        });
    };
    Replayer.prototype.applyScroll = function (d, isSync) {
        var target = this.mirror.getNode(d.id);
        if (!target) {
            return this.debugNodeNotFound(d, d.id);
        }
        if (target === this.iframe.contentDocument) {
            this.iframe.contentWindow.scrollTo({
                top: d.y,
                left: d.x,
                behavior: isSync ? 'auto' : 'smooth',
            });
        }
        else if (target.__sn.type === rrwebSnapshot.NodeType.Document) {
            target.defaultView.scrollTo({
                top: d.y,
                left: d.x,
                behavior: isSync ? 'auto' : 'smooth',
            });
        }
        else {
            try {
                target.scrollTop = d.y;
                target.scrollLeft = d.x;
            }
            catch (error) {
            }
        }
    };
    Replayer.prototype.applyInput = function (d) {
        var target = this.mirror.getNode(d.id);
        if (!target) {
            return this.debugNodeNotFound(d, d.id);
        }
        try {
            target.checked = d.isChecked;
            target.value = d.text;
        }
        catch (error) {
        }
    };
    Replayer.prototype.applyText = function (d, mutation) {
        var target = this.mirror.getNode(d.id);
        if (!target) {
            return this.debugNodeNotFound(mutation, d.id);
        }
        try {
            target.textContent = d.value;
        }
        catch (error) {
        }
    };
    Replayer.prototype.legacy_resolveMissingNode = function (map, parent, target, targetMutation) {
        var previousId = targetMutation.previousId, nextId = targetMutation.nextId;
        var previousInMap = previousId && map[previousId];
        var nextInMap = nextId && map[nextId];
        if (previousInMap) {
            var _a = previousInMap, node = _a.node, mutation = _a.mutation;
            parent.insertBefore(node, target);
            delete map[mutation.node.id];
            delete this.legacy_missingNodeRetryMap[mutation.node.id];
            if (mutation.previousId || mutation.nextId) {
                this.legacy_resolveMissingNode(map, parent, node, mutation);
            }
        }
        if (nextInMap) {
            var _b = nextInMap, node = _b.node, mutation = _b.mutation;
            parent.insertBefore(node, target.nextSibling);
            delete map[mutation.node.id];
            delete this.legacy_missingNodeRetryMap[mutation.node.id];
            if (mutation.previousId || mutation.nextId) {
                this.legacy_resolveMissingNode(map, parent, node, mutation);
            }
        }
    };
    Replayer.prototype.moveAndHover = function (x, y, id, isSync, debugData) {
        var target = this.mirror.getNode(id);
        if (!target) {
            return this.debugNodeNotFound(debugData, id);
        }
        var base = utils.getBaseDimension(target, this.iframe);
        var _x = x * base.absoluteScale + base.x;
        var _y = y * base.absoluteScale + base.y;
        this.mouse.style.left = "".concat(_x, "px");
        this.mouse.style.top = "".concat(_y, "px");
        if (!isSync) {
            this.drawMouseTail({ x: _x, y: _y });
        }
        this.hoverElements(target);
    };
    Replayer.prototype.drawMouseTail = function (position) {
        var _this = this;
        if (!this.mouseTail) {
            return;
        }
        var _a = this.config.mouseTail === true
            ? defaultMouseTailConfig
            : Object.assign({}, defaultMouseTailConfig, this.config.mouseTail), lineCap = _a.lineCap, lineWidth = _a.lineWidth, strokeStyle = _a.strokeStyle, duration = _a.duration;
        var draw = function () {
            if (!_this.mouseTail) {
                return;
            }
            var ctx = _this.mouseTail.getContext('2d');
            if (!ctx || !_this.tailPositions.length) {
                return;
            }
            ctx.clearRect(0, 0, _this.mouseTail.width, _this.mouseTail.height);
            ctx.beginPath();
            ctx.lineWidth = lineWidth;
            ctx.lineCap = lineCap;
            ctx.strokeStyle = strokeStyle;
            ctx.moveTo(_this.tailPositions[0].x, _this.tailPositions[0].y);
            _this.tailPositions.forEach(function (p) { return ctx.lineTo(p.x, p.y); });
            ctx.stroke();
        };
        this.tailPositions.push(position);
        draw();
        setTimeout(function () {
            _this.tailPositions = _this.tailPositions.filter(function (p) { return p !== position; });
            draw();
        }, duration / this.speedService.state.context.timer.speed);
    };
    Replayer.prototype.hoverElements = function (el) {
        var _a;
        (_a = this.iframe.contentDocument) === null || _a === void 0 ? void 0 : _a.querySelectorAll('.\\:hover').forEach(function (hoveredEl) {
            hoveredEl.classList.remove(':hover');
        });
        var currentEl = el;
        while (currentEl) {
            if (currentEl.classList) {
                currentEl.classList.add(':hover');
            }
            currentEl = currentEl.parentElement;
        }
    };
    Replayer.prototype.isUserInteraction = function (event) {
        if (event.type !== types.EventType.IncrementalSnapshot) {
            return false;
        }
        return (event.data.source > types.IncrementalSource.Mutation &&
            event.data.source <= types.IncrementalSource.Input);
    };
    Replayer.prototype.backToNormal = function () {
        this.nextUserInteractionEvent = null;
        if (this.speedService.state.matches('normal')) {
            return;
        }
        this.speedService.send({ type: 'BACK_TO_NORMAL' });
        this.emitter.emit(types.ReplayerEvents.SkipEnd, {
            speed: this.speedService.state.context.normalSpeed,
        });
    };
    Replayer.prototype.restoreRealParent = function (frag, parent) {
        this.mirror.map[parent.__sn.id] = parent;
        if (parent.__sn.type === rrwebSnapshot.NodeType.Element &&
            parent.__sn.tagName === 'textarea' &&
            frag.textContent) {
            parent.value = frag.textContent;
        }
        parent.appendChild(frag);
        this.restoreState(parent);
    };
    Replayer.prototype.storeState = function (parent) {
        var e_16, _a;
        if (parent) {
            if (parent.nodeType === parent.ELEMENT_NODE) {
                var parentElement = parent;
                if (parentElement.scrollLeft || parentElement.scrollTop) {
                    this.elementStateMap.set(parent, {
                        scroll: [parentElement.scrollLeft, parentElement.scrollTop],
                    });
                }
                if (parentElement.tagName === 'STYLE')
                    virtualStyles.storeCSSRules(parentElement, this.virtualStyleRulesMap);
                var children = parentElement.children;
                try {
                    for (var _b = tslib_es6.__values(Array.from(children)), _c = _b.next(); !_c.done; _c = _b.next()) {
                        var child = _c.value;
                        this.storeState(child);
                    }
                }
                catch (e_16_1) { e_16 = { error: e_16_1 }; }
                finally {
                    try {
                        if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
                    }
                    finally { if (e_16) throw e_16.error; }
                }
            }
        }
    };
    Replayer.prototype.restoreState = function (parent) {
        var e_17, _a;
        if (parent.nodeType === parent.ELEMENT_NODE) {
            var parentElement = parent;
            if (this.elementStateMap.has(parent)) {
                var storedState = this.elementStateMap.get(parent);
                if (storedState.scroll) {
                    parentElement.scrollLeft = storedState.scroll[0];
                    parentElement.scrollTop = storedState.scroll[1];
                }
                this.elementStateMap.delete(parent);
            }
            var children = parentElement.children;
            try {
                for (var _b = tslib_es6.__values(Array.from(children)), _c = _b.next(); !_c.done; _c = _b.next()) {
                    var child = _c.value;
                    this.restoreState(child);
                }
            }
            catch (e_17_1) { e_17 = { error: e_17_1 }; }
            finally {
                try {
                    if (_c && !_c.done && (_a = _b.return)) _a.call(_b);
                }
                finally { if (e_17) throw e_17.error; }
            }
        }
    };
    Replayer.prototype.restoreNodeSheet = function (node) {
        var storedRules = this.virtualStyleRulesMap.get(node);
        if (node.nodeName !== 'STYLE') {
            return;
        }
        if (!storedRules) {
            return;
        }
        var styleNode = node;
        virtualStyles.applyVirtualStyleRulesToNode(storedRules, styleNode);
    };
    Replayer.prototype.warnNodeNotFound = function (d, id) {
        if (this.treeIndex.idRemoved(id)) {
            this.warn("Node with id '".concat(id, "' was previously removed. "), d);
        }
        else {
            this.warn("Node with id '".concat(id, "' not found. "), d);
        }
    };
    Replayer.prototype.warnCanvasMutationFailed = function (d, error) {
        this.warn("Has error on canvas update", error, 'canvas mutation:', d);
    };
    Replayer.prototype.debugNodeNotFound = function (d, id) {
        if (this.treeIndex.idRemoved(id)) {
            this.debug(REPLAY_CONSOLE_PREFIX, "Node with id '".concat(id, "' was previously removed. "), d);
        }
        else {
            this.debug(REPLAY_CONSOLE_PREFIX, "Node with id '".concat(id, "' not found. "), d);
        }
    };
    Replayer.prototype.warn = function () {
        var args = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            args[_i] = arguments[_i];
        }
        if (!this.config.showWarning) {
            return;
        }
        console.warn.apply(console, tslib_es6.__spreadArray([REPLAY_CONSOLE_PREFIX], tslib_es6.__read(args), false));
    };
    Replayer.prototype.debug = function () {
        var args = [];
        for (var _i = 0; _i < arguments.length; _i++) {
            args[_i] = arguments[_i];
        }
        if (!this.config.showDebug) {
            return;
        }
        console.log.apply(console, tslib_es6.__spreadArray([REPLAY_CONSOLE_PREFIX], tslib_es6.__read(args), false));
    };
    return Replayer;
}());

exports.Replayer = Replayer;


},{"../../../../ext/mitt/dist/mitt.es.js":53,"../../../rrweb-snapshot/es/rrweb-snapshot.js":54,"../../ext/tslib/tslib.es6.js":55,"../types.js":84,"../utils.js":85,"./canvas/index.js":76,"./machine.js":79,"./smoothscroll.js":80,"./styles/inject-style.js":81,"./timer.js":82,"./virtual-styles.js":83}],79:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');
const index = require('../../../../ext/@xstate/fsm/es/index.js');
const types = require('../types.js');
const timer = require('./timer.js');

function discardPriorSnapshots(events, baselineTime) {
    for (var idx = events.length - 1; idx >= 0; idx--) {
        var event_1 = events[idx];
        if (event_1.type === types.EventType.Meta) {
            if (event_1.timestamp <= baselineTime) {
                return events.slice(idx);
            }
        }
    }
    return events;
}
function createPlayerService(context, _a) {
    var getCastFn = _a.getCastFn, applyEventsSynchronously = _a.applyEventsSynchronously, emitter = _a.emitter;
    var playerMachine = index.createMachine({
        id: 'player',
        context: context,
        initial: 'paused',
        states: {
            playing: {
                on: {
                    PAUSE: {
                        target: 'paused',
                        actions: ['pause'],
                    },
                    CAST_EVENT: {
                        target: 'playing',
                        actions: 'castEvent',
                    },
                    END: {
                        target: 'paused',
                        actions: ['resetLastPlayedEvent', 'pause'],
                    },
                    ADD_EVENT: {
                        target: 'playing',
                        actions: ['addEvent'],
                    },
                },
            },
            paused: {
                on: {
                    PLAY: {
                        target: 'playing',
                        actions: ['recordTimeOffset', 'play'],
                    },
                    CAST_EVENT: {
                        target: 'paused',
                        actions: 'castEvent',
                    },
                    TO_LIVE: {
                        target: 'live',
                        actions: ['startLive'],
                    },
                    ADD_EVENT: {
                        target: 'paused',
                        actions: ['addEvent'],
                    },
                },
            },
            live: {
                on: {
                    ADD_EVENT: {
                        target: 'live',
                        actions: ['addEvent'],
                    },
                    CAST_EVENT: {
                        target: 'live',
                        actions: ['castEvent'],
                    },
                },
            },
        },
    }, {
        actions: {
            castEvent: index.assign({
                lastPlayedEvent: function (ctx, event) {
                    if (event.type === 'CAST_EVENT') {
                        return event.payload.event;
                    }
                    return ctx.lastPlayedEvent;
                },
            }),
            recordTimeOffset: index.assign(function (ctx, event) {
                var timeOffset = ctx.timeOffset;
                if ('payload' in event && 'timeOffset' in event.payload) {
                    timeOffset = event.payload.timeOffset;
                }
                return tslib_es6.__assign(tslib_es6.__assign({}, ctx), { timeOffset: timeOffset, baselineTime: ctx.events[0].timestamp + timeOffset });
            }),
            play: function (ctx) {
                var e_1, _a, e_2, _b;
                var _c;
                var timer$1 = ctx.timer, events = ctx.events, baselineTime = ctx.baselineTime, lastPlayedEvent = ctx.lastPlayedEvent;
                timer$1.clear();
                try {
                    for (var events_1 = tslib_es6.__values(events), events_1_1 = events_1.next(); !events_1_1.done; events_1_1 = events_1.next()) {
                        var event_2 = events_1_1.value;
                        timer.addDelay(event_2, baselineTime);
                    }
                }
                catch (e_1_1) { e_1 = { error: e_1_1 }; }
                finally {
                    try {
                        if (events_1_1 && !events_1_1.done && (_a = events_1.return)) _a.call(events_1);
                    }
                    finally { if (e_1) throw e_1.error; }
                }
                var neededEvents = discardPriorSnapshots(events, baselineTime);
                var lastPlayedTimestamp = lastPlayedEvent === null || lastPlayedEvent === void 0 ? void 0 : lastPlayedEvent.timestamp;
                if ((lastPlayedEvent === null || lastPlayedEvent === void 0 ? void 0 : lastPlayedEvent.type) === types.EventType.IncrementalSnapshot &&
                    lastPlayedEvent.data.source === types.IncrementalSource.MouseMove) {
                    lastPlayedTimestamp =
                        lastPlayedEvent.timestamp +
                            ((_c = lastPlayedEvent.data.positions[0]) === null || _c === void 0 ? void 0 : _c.timeOffset);
                }
                if (baselineTime < (lastPlayedTimestamp || 0)) {
                    emitter.emit(types.ReplayerEvents.PlayBack);
                }
                var syncEvents = new Array();
                var actions = new Array();
                var _loop_1 = function (event_3) {
                    if (lastPlayedTimestamp &&
                        lastPlayedTimestamp < baselineTime &&
                        (event_3.timestamp <= lastPlayedTimestamp ||
                            event_3 === lastPlayedEvent)) {
                        return "continue";
                    }
                    if (event_3.timestamp < baselineTime) {
                        syncEvents.push(event_3);
                    }
                    else {
                        var castFn_1 = getCastFn(event_3, false);
                        actions.push({
                            doAction: function () {
                                castFn_1();
                            },
                            delay: event_3.delay,
                        });
                    }
                };
                try {
                    for (var neededEvents_1 = tslib_es6.__values(neededEvents), neededEvents_1_1 = neededEvents_1.next(); !neededEvents_1_1.done; neededEvents_1_1 = neededEvents_1.next()) {
                        var event_3 = neededEvents_1_1.value;
                        _loop_1(event_3);
                    }
                }
                catch (e_2_1) { e_2 = { error: e_2_1 }; }
                finally {
                    try {
                        if (neededEvents_1_1 && !neededEvents_1_1.done && (_b = neededEvents_1.return)) _b.call(neededEvents_1);
                    }
                    finally { if (e_2) throw e_2.error; }
                }
                applyEventsSynchronously(syncEvents);
                emitter.emit(types.ReplayerEvents.Flush);
                timer$1.addActions(actions);
                timer$1.start();
            },
            pause: function (ctx) {
                ctx.timer.clear();
            },
            resetLastPlayedEvent: index.assign(function (ctx) {
                return tslib_es6.__assign(tslib_es6.__assign({}, ctx), { lastPlayedEvent: null });
            }),
            startLive: index.assign({
                baselineTime: function (ctx, event) {
                    ctx.timer.toggleLiveMode(true);
                    ctx.timer.start();
                    if (event.type === 'TO_LIVE' && event.payload.baselineTime) {
                        return event.payload.baselineTime;
                    }
                    return Date.now();
                },
            }),
            addEvent: index.assign(function (ctx, machineEvent) {
                var baselineTime = ctx.baselineTime, timer$1 = ctx.timer, events = ctx.events;
                if (machineEvent.type === 'ADD_EVENT') {
                    var event_4 = machineEvent.payload.event;
                    timer.addDelay(event_4, baselineTime);
                    var end = events.length - 1;
                    if (!events[end] || events[end].timestamp <= event_4.timestamp) {
                        events.push(event_4);
                    }
                    else {
                        var insertionIndex = -1;
                        var start = 0;
                        while (start <= end) {
                            var mid = Math.floor((start + end) / 2);
                            if (events[mid].timestamp <= event_4.timestamp) {
                                start = mid + 1;
                            }
                            else {
                                end = mid - 1;
                            }
                        }
                        if (insertionIndex === -1) {
                            insertionIndex = start;
                        }
                        events.splice(insertionIndex, 0, event_4);
                    }
                    var isSync = event_4.timestamp < baselineTime;
                    var castFn_2 = getCastFn(event_4, isSync);
                    if (isSync) {
                        castFn_2();
                    }
                    else if (timer$1.isActive()) {
                        timer$1.addAction({
                            doAction: function () {
                                castFn_2();
                            },
                            delay: event_4.delay,
                        });
                    }
                }
                return tslib_es6.__assign(tslib_es6.__assign({}, ctx), { events: events });
            }),
        },
    });
    return index.interpret(playerMachine);
}
function createSpeedService(context) {
    var speedMachine = index.createMachine({
        id: 'speed',
        context: context,
        initial: 'normal',
        states: {
            normal: {
                on: {
                    FAST_FORWARD: {
                        target: 'skipping',
                        actions: ['recordSpeed', 'setSpeed'],
                    },
                    SET_SPEED: {
                        target: 'normal',
                        actions: ['setSpeed'],
                    },
                },
            },
            skipping: {
                on: {
                    BACK_TO_NORMAL: {
                        target: 'normal',
                        actions: ['restoreSpeed'],
                    },
                    SET_SPEED: {
                        target: 'normal',
                        actions: ['setSpeed'],
                    },
                },
            },
        },
    }, {
        actions: {
            setSpeed: function (ctx, event) {
                if ('payload' in event) {
                    ctx.timer.setSpeed(event.payload.speed);
                }
            },
            recordSpeed: index.assign({
                normalSpeed: function (ctx) { return ctx.timer.speed; },
            }),
            restoreSpeed: function (ctx) {
                ctx.timer.setSpeed(ctx.normalSpeed);
            },
        },
    });
    return index.interpret(speedMachine);
}

exports.createPlayerService = createPlayerService;
exports.createSpeedService = createSpeedService;
exports.discardPriorSnapshots = discardPriorSnapshots;


},{"../../../../ext/@xstate/fsm/es/index.js":50,"../../ext/tslib/tslib.es6.js":55,"../types.js":84,"./timer.js":82}],80:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

function polyfill(w, d) {
    if (w === void 0) { w = window; }
    if (d === void 0) { d = document; }
    if ('scrollBehavior' in d.documentElement.style &&
        w.__forceSmoothScrollPolyfill__ !== true) {
        return;
    }
    var Element = w.HTMLElement || w.Element;
    var SCROLL_TIME = 468;
    var original = {
        scroll: w.scroll || w.scrollTo,
        scrollBy: w.scrollBy,
        elementScroll: Element.prototype.scroll || scrollElement,
        scrollIntoView: Element.prototype.scrollIntoView,
    };
    var now = w.performance && w.performance.now
        ? w.performance.now.bind(w.performance)
        : Date.now;
    function isMicrosoftBrowser(userAgent) {
        var userAgentPatterns = ['MSIE ', 'Trident/', 'Edge/'];
        return new RegExp(userAgentPatterns.join('|')).test(userAgent);
    }
    var ROUNDING_TOLERANCE = isMicrosoftBrowser(w.navigator.userAgent) ? 1 : 0;
    function scrollElement(x, y) {
        this.scrollLeft = x;
        this.scrollTop = y;
    }
    function ease(k) {
        return 0.5 * (1 - Math.cos(Math.PI * k));
    }
    function shouldBailOut(firstArg) {
        if (firstArg === null ||
            typeof firstArg !== 'object' ||
            firstArg.behavior === undefined ||
            firstArg.behavior === 'auto' ||
            firstArg.behavior === 'instant') {
            return true;
        }
        if (typeof firstArg === 'object' && firstArg.behavior === 'smooth') {
            return false;
        }
        throw new TypeError('behavior member of ScrollOptions ' +
            firstArg.behavior +
            ' is not a valid value for enumeration ScrollBehavior.');
    }
    function hasScrollableSpace(el, axis) {
        if (axis === 'Y') {
            return el.clientHeight + ROUNDING_TOLERANCE < el.scrollHeight;
        }
        if (axis === 'X') {
            return el.clientWidth + ROUNDING_TOLERANCE < el.scrollWidth;
        }
    }
    function canOverflow(el, axis) {
        var overflowValue = w.getComputedStyle(el, null)['overflow' + axis];
        return overflowValue === 'auto' || overflowValue === 'scroll';
    }
    function isScrollable(el) {
        var isScrollableY = hasScrollableSpace(el, 'Y') && canOverflow(el, 'Y');
        var isScrollableX = hasScrollableSpace(el, 'X') && canOverflow(el, 'X');
        return isScrollableY || isScrollableX;
    }
    function findScrollableParent(el) {
        while (el !== d.body && isScrollable(el) === false) {
            el = el.parentNode || el.host;
        }
        return el;
    }
    function step(context) {
        var time = now();
        var value;
        var currentX;
        var currentY;
        var elapsed = (time - context.startTime) / SCROLL_TIME;
        elapsed = elapsed > 1 ? 1 : elapsed;
        value = ease(elapsed);
        currentX = context.startX + (context.x - context.startX) * value;
        currentY = context.startY + (context.y - context.startY) * value;
        context.method.call(context.scrollable, currentX, currentY);
        if (currentX !== context.x || currentY !== context.y) {
            w.requestAnimationFrame(step.bind(w, context));
        }
    }
    function smoothScroll(el, x, y) {
        var scrollable;
        var startX;
        var startY;
        var method;
        var startTime = now();
        if (el === d.body) {
            scrollable = w;
            startX = w.scrollX || w.pageXOffset;
            startY = w.scrollY || w.pageYOffset;
            method = original.scroll;
        }
        else {
            scrollable = el;
            startX = el.scrollLeft;
            startY = el.scrollTop;
            method = scrollElement;
        }
        step({
            scrollable: scrollable,
            method: method,
            startTime: startTime,
            startX: startX,
            startY: startY,
            x: x,
            y: y,
        });
    }
    w.scroll = w.scrollTo = function () {
        if (arguments[0] === undefined) {
            return;
        }
        if (shouldBailOut(arguments[0]) === true) {
            original.scroll.call(w, arguments[0].left !== undefined
                ? arguments[0].left
                : typeof arguments[0] !== 'object'
                    ? arguments[0]
                    : w.scrollX || w.pageXOffset, arguments[0].top !== undefined
                ? arguments[0].top
                : arguments[1] !== undefined
                    ? arguments[1]
                    : w.scrollY || w.pageYOffset);
            return;
        }
        smoothScroll.call(w, d.body, arguments[0].left !== undefined
            ? ~~arguments[0].left
            : w.scrollX || w.pageXOffset, arguments[0].top !== undefined
            ? ~~arguments[0].top
            : w.scrollY || w.pageYOffset);
    };
    w.scrollBy = function () {
        if (arguments[0] === undefined) {
            return;
        }
        if (shouldBailOut(arguments[0])) {
            original.scrollBy.call(w, arguments[0].left !== undefined
                ? arguments[0].left
                : typeof arguments[0] !== 'object'
                    ? arguments[0]
                    : 0, arguments[0].top !== undefined
                ? arguments[0].top
                : arguments[1] !== undefined
                    ? arguments[1]
                    : 0);
            return;
        }
        smoothScroll.call(w, d.body, ~~arguments[0].left + (w.scrollX || w.pageXOffset), ~~arguments[0].top + (w.scrollY || w.pageYOffset));
    };
    Element.prototype.scroll = Element.prototype.scrollTo = function () {
        if (arguments[0] === undefined) {
            return;
        }
        if (shouldBailOut(arguments[0]) === true) {
            if (typeof arguments[0] === 'number' && arguments[1] === undefined) {
                throw new SyntaxError('Value could not be converted');
            }
            original.elementScroll.call(this, arguments[0].left !== undefined
                ? ~~arguments[0].left
                : typeof arguments[0] !== 'object'
                    ? ~~arguments[0]
                    : this.scrollLeft, arguments[0].top !== undefined
                ? ~~arguments[0].top
                : arguments[1] !== undefined
                    ? ~~arguments[1]
                    : this.scrollTop);
            return;
        }
        var left = arguments[0].left;
        var top = arguments[0].top;
        smoothScroll.call(this, this, typeof left === 'undefined' ? this.scrollLeft : ~~left, typeof top === 'undefined' ? this.scrollTop : ~~top);
    };
    Element.prototype.scrollBy = function () {
        if (arguments[0] === undefined) {
            return;
        }
        if (shouldBailOut(arguments[0]) === true) {
            original.elementScroll.call(this, arguments[0].left !== undefined
                ? ~~arguments[0].left + this.scrollLeft
                : ~~arguments[0] + this.scrollLeft, arguments[0].top !== undefined
                ? ~~arguments[0].top + this.scrollTop
                : ~~arguments[1] + this.scrollTop);
            return;
        }
        this.scroll({
            left: ~~arguments[0].left + this.scrollLeft,
            top: ~~arguments[0].top + this.scrollTop,
            behavior: arguments[0].behavior,
        });
    };
    Element.prototype.scrollIntoView = function () {
        if (shouldBailOut(arguments[0]) === true) {
            original.scrollIntoView.call(this, arguments[0] === undefined ? true : arguments[0]);
            return;
        }
        var scrollableParent = findScrollableParent(this);
        var parentRects = scrollableParent.getBoundingClientRect();
        var clientRects = this.getBoundingClientRect();
        if (scrollableParent !== d.body) {
            smoothScroll.call(this, scrollableParent, scrollableParent.scrollLeft + clientRects.left - parentRects.left, scrollableParent.scrollTop + clientRects.top - parentRects.top);
            if (w.getComputedStyle(scrollableParent).position !== 'fixed') {
                w.scrollBy({
                    left: parentRects.left,
                    top: parentRects.top,
                    behavior: 'smooth',
                });
            }
        }
        else {
            w.scrollBy({
                left: clientRects.left,
                top: clientRects.top,
                behavior: 'smooth',
            });
        }
    };
}

exports.polyfill = polyfill;


},{}],81:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

var rules = function (blockClass) { return [
    ".".concat(blockClass, " { background: currentColor }"),
    'noscript { display: none !important; }',
]; };

exports.default = rules;


},{}],82:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const types = require('../types.js');

var Timer = (function () {
    function Timer(actions, speed) {
        if (actions === void 0) { actions = []; }
        this.timeOffset = 0;
        this.raf = null;
        this.actions = actions;
        this.speed = speed;
    }
    Timer.prototype.addAction = function (action) {
        var index = this.findActionIndex(action);
        this.actions.splice(index, 0, action);
    };
    Timer.prototype.addActions = function (actions) {
        this.actions = this.actions.concat(actions);
    };
    Timer.prototype.start = function () {
        this.timeOffset = 0;
        var lastTimestamp = performance.now();
        var actions = this.actions;
        var self = this;
        function check() {
            var time = performance.now();
            self.timeOffset += (time - lastTimestamp) * self.speed;
            lastTimestamp = time;
            while (actions.length) {
                var action = actions[0];
                if (self.timeOffset >= action.delay) {
                    actions.shift();
                    action.doAction();
                }
                else {
                    break;
                }
            }
            if (actions.length > 0 || self.liveMode) {
                self.raf = requestAnimationFrame(check);
            }
        }
        this.raf = requestAnimationFrame(check);
    };
    Timer.prototype.clear = function () {
        if (this.raf) {
            cancelAnimationFrame(this.raf);
            this.raf = null;
        }
        this.actions.length = 0;
    };
    Timer.prototype.setSpeed = function (speed) {
        this.speed = speed;
    };
    Timer.prototype.toggleLiveMode = function (mode) {
        this.liveMode = mode;
    };
    Timer.prototype.isActive = function () {
        return this.raf !== null;
    };
    Timer.prototype.findActionIndex = function (action) {
        var start = 0;
        var end = this.actions.length - 1;
        while (start <= end) {
            var mid = Math.floor((start + end) / 2);
            if (this.actions[mid].delay < action.delay) {
                start = mid + 1;
            }
            else if (this.actions[mid].delay > action.delay) {
                end = mid - 1;
            }
            else {
                return mid + 1;
            }
        }
        return start;
    };
    return Timer;
}());
function addDelay(event, baselineTime) {
    if (event.type === types.EventType.IncrementalSnapshot &&
        event.data.source === types.IncrementalSource.MouseMove) {
        var firstOffset = event.data.positions[0].timeOffset;
        var firstTimestamp = event.timestamp + firstOffset;
        event.delay = firstTimestamp - baselineTime;
        return firstTimestamp - baselineTime;
    }
    event.delay = event.timestamp - baselineTime;
    return event.delay;
}

exports.Timer = Timer;
exports.addDelay = addDelay;


},{"../types.js":84}],83:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../../ext/tslib/tslib.es6.js');

exports.StyleRuleType = void 0;
(function (StyleRuleType) {
    StyleRuleType[StyleRuleType["Insert"] = 0] = "Insert";
    StyleRuleType[StyleRuleType["Remove"] = 1] = "Remove";
    StyleRuleType[StyleRuleType["Snapshot"] = 2] = "Snapshot";
    StyleRuleType[StyleRuleType["SetProperty"] = 3] = "SetProperty";
    StyleRuleType[StyleRuleType["RemoveProperty"] = 4] = "RemoveProperty";
})(exports.StyleRuleType || (exports.StyleRuleType = {}));
function getNestedRule(rules, position) {
    var rule = rules[position[0]];
    if (position.length === 1) {
        return rule;
    }
    else {
        return getNestedRule(rule.cssRules[position[1]]
            .cssRules, position.slice(2));
    }
}
function getPositionsAndIndex(nestedIndex) {
    var positions = tslib_es6.__spreadArray([], tslib_es6.__read(nestedIndex), false);
    var index = positions.pop();
    return { positions: positions, index: index };
}
function applyVirtualStyleRulesToNode(storedRules, styleNode) {
    var sheet = styleNode.sheet;
    if (!sheet) {
        return;
    }
    storedRules.forEach(function (rule) {
        if (rule.type === exports.StyleRuleType.Insert) {
            try {
                if (Array.isArray(rule.index)) {
                    var _a = getPositionsAndIndex(rule.index), positions = _a.positions, index = _a.index;
                    var nestedRule = getNestedRule(sheet.cssRules, positions);
                    nestedRule.insertRule(rule.cssText, index);
                }
                else {
                    sheet.insertRule(rule.cssText, rule.index);
                }
            }
            catch (e) {
            }
        }
        else if (rule.type === exports.StyleRuleType.Remove) {
            try {
                if (Array.isArray(rule.index)) {
                    var _b = getPositionsAndIndex(rule.index), positions = _b.positions, index = _b.index;
                    var nestedRule = getNestedRule(sheet.cssRules, positions);
                    nestedRule.deleteRule(index || 0);
                }
                else {
                    sheet.deleteRule(rule.index);
                }
            }
            catch (e) {
            }
        }
        else if (rule.type === exports.StyleRuleType.Snapshot) {
            restoreSnapshotOfStyleRulesToNode(rule.cssTexts, styleNode);
        }
        else if (rule.type === exports.StyleRuleType.SetProperty) {
            var nativeRule = getNestedRule(sheet.cssRules, rule.index);
            nativeRule.style.setProperty(rule.property, rule.value, rule.priority);
        }
        else if (rule.type === exports.StyleRuleType.RemoveProperty) {
            var nativeRule = getNestedRule(sheet.cssRules, rule.index);
            nativeRule.style.removeProperty(rule.property);
        }
    });
}
function restoreSnapshotOfStyleRulesToNode(cssTexts, styleNode) {
    var _a;
    try {
        var existingRules = Array.from(((_a = styleNode.sheet) === null || _a === void 0 ? void 0 : _a.cssRules) || []).map(function (rule) { return rule.cssText; });
        var existingRulesReversed = Object.entries(existingRules).reverse();
        var lastMatch_1 = existingRules.length;
        existingRulesReversed.forEach(function (_a) {
            var _b;
            var _c = tslib_es6.__read(_a, 2), index = _c[0], rule = _c[1];
            var indexOf = cssTexts.indexOf(rule);
            if (indexOf === -1 || indexOf > lastMatch_1) {
                try {
                    (_b = styleNode.sheet) === null || _b === void 0 ? void 0 : _b.deleteRule(Number(index));
                }
                catch (e) {
                }
            }
            lastMatch_1 = indexOf;
        });
        cssTexts.forEach(function (cssText, index) {
            var _a, _b, _c;
            try {
                if (((_b = (_a = styleNode.sheet) === null || _a === void 0 ? void 0 : _a.cssRules[index]) === null || _b === void 0 ? void 0 : _b.cssText) !== cssText) {
                    (_c = styleNode.sheet) === null || _c === void 0 ? void 0 : _c.insertRule(cssText, index);
                }
            }
            catch (e) {
            }
        });
    }
    catch (e) {
    }
}
function storeCSSRules(parentElement, virtualStyleRulesMap) {
    var _a;
    try {
        var cssTexts = Array.from(((_a = parentElement.sheet) === null || _a === void 0 ? void 0 : _a.cssRules) || []).map(function (rule) { return rule.cssText; });
        virtualStyleRulesMap.set(parentElement, [
            {
                type: exports.StyleRuleType.Snapshot,
                cssTexts: cssTexts,
            },
        ]);
    }
    catch (e) {
    }
}

exports.applyVirtualStyleRulesToNode = applyVirtualStyleRulesToNode;
exports.getNestedRule = getNestedRule;
exports.getPositionsAndIndex = getPositionsAndIndex;
exports.storeCSSRules = storeCSSRules;


},{"../../ext/tslib/tslib.es6.js":55}],84:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

exports.EventType = void 0;
(function (EventType) {
    EventType[EventType["DomContentLoaded"] = 0] = "DomContentLoaded";
    EventType[EventType["Load"] = 1] = "Load";
    EventType[EventType["FullSnapshot"] = 2] = "FullSnapshot";
    EventType[EventType["IncrementalSnapshot"] = 3] = "IncrementalSnapshot";
    EventType[EventType["Meta"] = 4] = "Meta";
    EventType[EventType["Custom"] = 5] = "Custom";
    EventType[EventType["Plugin"] = 6] = "Plugin";
})(exports.EventType || (exports.EventType = {}));
exports.IncrementalSource = void 0;
(function (IncrementalSource) {
    IncrementalSource[IncrementalSource["Mutation"] = 0] = "Mutation";
    IncrementalSource[IncrementalSource["MouseMove"] = 1] = "MouseMove";
    IncrementalSource[IncrementalSource["MouseInteraction"] = 2] = "MouseInteraction";
    IncrementalSource[IncrementalSource["Scroll"] = 3] = "Scroll";
    IncrementalSource[IncrementalSource["ViewportResize"] = 4] = "ViewportResize";
    IncrementalSource[IncrementalSource["Input"] = 5] = "Input";
    IncrementalSource[IncrementalSource["TouchMove"] = 6] = "TouchMove";
    IncrementalSource[IncrementalSource["MediaInteraction"] = 7] = "MediaInteraction";
    IncrementalSource[IncrementalSource["StyleSheetRule"] = 8] = "StyleSheetRule";
    IncrementalSource[IncrementalSource["CanvasMutation"] = 9] = "CanvasMutation";
    IncrementalSource[IncrementalSource["Font"] = 10] = "Font";
    IncrementalSource[IncrementalSource["Log"] = 11] = "Log";
    IncrementalSource[IncrementalSource["Drag"] = 12] = "Drag";
    IncrementalSource[IncrementalSource["StyleDeclaration"] = 13] = "StyleDeclaration";
})(exports.IncrementalSource || (exports.IncrementalSource = {}));
exports.MouseInteractions = void 0;
(function (MouseInteractions) {
    MouseInteractions[MouseInteractions["MouseUp"] = 0] = "MouseUp";
    MouseInteractions[MouseInteractions["MouseDown"] = 1] = "MouseDown";
    MouseInteractions[MouseInteractions["Click"] = 2] = "Click";
    MouseInteractions[MouseInteractions["ContextMenu"] = 3] = "ContextMenu";
    MouseInteractions[MouseInteractions["DblClick"] = 4] = "DblClick";
    MouseInteractions[MouseInteractions["Focus"] = 5] = "Focus";
    MouseInteractions[MouseInteractions["Blur"] = 6] = "Blur";
    MouseInteractions[MouseInteractions["TouchStart"] = 7] = "TouchStart";
    MouseInteractions[MouseInteractions["TouchMove_Departed"] = 8] = "TouchMove_Departed";
    MouseInteractions[MouseInteractions["TouchEnd"] = 9] = "TouchEnd";
    MouseInteractions[MouseInteractions["TouchCancel"] = 10] = "TouchCancel";
})(exports.MouseInteractions || (exports.MouseInteractions = {}));
exports.CanvasContext = void 0;
(function (CanvasContext) {
    CanvasContext[CanvasContext["2D"] = 0] = "2D";
    CanvasContext[CanvasContext["WebGL"] = 1] = "WebGL";
    CanvasContext[CanvasContext["WebGL2"] = 2] = "WebGL2";
})(exports.CanvasContext || (exports.CanvasContext = {}));
exports.MediaInteractions = void 0;
(function (MediaInteractions) {
    MediaInteractions[MediaInteractions["Play"] = 0] = "Play";
    MediaInteractions[MediaInteractions["Pause"] = 1] = "Pause";
    MediaInteractions[MediaInteractions["Seeked"] = 2] = "Seeked";
    MediaInteractions[MediaInteractions["VolumeChange"] = 3] = "VolumeChange";
})(exports.MediaInteractions || (exports.MediaInteractions = {}));
exports.ReplayerEvents = void 0;
(function (ReplayerEvents) {
    ReplayerEvents["Start"] = "start";
    ReplayerEvents["Pause"] = "pause";
    ReplayerEvents["Resume"] = "resume";
    ReplayerEvents["Resize"] = "resize";
    ReplayerEvents["Finish"] = "finish";
    ReplayerEvents["FullsnapshotRebuilded"] = "fullsnapshot-rebuilded";
    ReplayerEvents["LoadStylesheetStart"] = "load-stylesheet-start";
    ReplayerEvents["LoadStylesheetEnd"] = "load-stylesheet-end";
    ReplayerEvents["SkipStart"] = "skip-start";
    ReplayerEvents["SkipEnd"] = "skip-end";
    ReplayerEvents["MouseInteraction"] = "mouse-interaction";
    ReplayerEvents["EventCast"] = "event-cast";
    ReplayerEvents["CustomEvent"] = "custom-event";
    ReplayerEvents["Flush"] = "flush";
    ReplayerEvents["StateChange"] = "state-change";
    ReplayerEvents["PlayBack"] = "play-back";
})(exports.ReplayerEvents || (exports.ReplayerEvents = {}));


},{}],85:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const tslib_es6 = require('../ext/tslib/tslib.es6.js');
const types = require('./types.js');
const rrwebSnapshot = require('../../rrweb-snapshot/es/rrweb-snapshot.js');

function on(type, fn, target) {
    if (target === void 0) { target = document; }
    var options = { capture: true, passive: true };
    target.addEventListener(type, fn, options);
    return function () { return target.removeEventListener(type, fn, options); };
}
function createMirror() {
    return {
        map: {},
        getId: function (n) {
            if (!n || !n.__sn) {
                return -1;
            }
            return n.__sn.id;
        },
        getNode: function (id) {
            return this.map[id] || null;
        },
        removeNodeFromMap: function (n) {
            var _this = this;
            var id = n.__sn && n.__sn.id;
            delete this.map[id];
            if (n.childNodes) {
                n.childNodes.forEach(function (child) {
                    return _this.removeNodeFromMap(child);
                });
            }
        },
        has: function (id) {
            return this.map.hasOwnProperty(id);
        },
        reset: function () {
            this.map = {};
        },
    };
}
var DEPARTED_MIRROR_ACCESS_WARNING = 'Please stop import mirror directly. Instead of that,' +
    '\r\n' +
    'now you can use replayer.getMirror() to access the mirror instance of a replayer,' +
    '\r\n' +
    'or you can use record.mirror to access the mirror instance during recording.';
exports._mirror = {
    map: {},
    getId: function () {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
        return -1;
    },
    getNode: function () {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
        return null;
    },
    removeNodeFromMap: function () {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
    },
    has: function () {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
        return false;
    },
    reset: function () {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
    },
};
if (typeof window !== 'undefined' && window.Proxy && window.Reflect) {
    exports._mirror = new Proxy(exports._mirror, {
        get: function (target, prop, receiver) {
            if (prop === 'map') {
                console.error(DEPARTED_MIRROR_ACCESS_WARNING);
            }
            return Reflect.get(target, prop, receiver);
        },
    });
}
function throttle(func, wait, options) {
    if (options === void 0) { options = {}; }
    var timeout = null;
    var previous = 0;
    return function (arg) {
        var now = Date.now();
        if (!previous && options.leading === false) {
            previous = now;
        }
        var remaining = wait - (now - previous);
        var context = this;
        var args = arguments;
        if (remaining <= 0 || remaining > wait) {
            if (timeout) {
                clearTimeout(timeout);
                timeout = null;
            }
            previous = now;
            func.apply(context, args);
        }
        else if (!timeout && options.trailing !== false) {
            timeout = setTimeout(function () {
                previous = options.leading === false ? 0 : Date.now();
                timeout = null;
                func.apply(context, args);
            }, remaining);
        }
    };
}
function hookSetter(target, key, d, isRevoked, win) {
    if (win === void 0) { win = window; }
    var original = win.Object.getOwnPropertyDescriptor(target, key);
    win.Object.defineProperty(target, key, isRevoked
        ? d
        : {
            set: function (value) {
                var _this = this;
                setTimeout(function () {
                    d.set.call(_this, value);
                }, 0);
                if (original && original.set) {
                    original.set.call(this, value);
                }
            },
        });
    return function () { return hookSetter(target, key, original || {}, true); };
}
function patch(source, name, replacement) {
    try {
        if (!(name in source)) {
            return function () { };
        }
        var original_1 = source[name];
        var wrapped = replacement(original_1);
        if (typeof wrapped === 'function') {
            wrapped.prototype = wrapped.prototype || {};
            Object.defineProperties(wrapped, {
                __rrweb_original__: {
                    enumerable: false,
                    value: original_1,
                },
            });
        }
        source[name] = wrapped;
        return function () {
            source[name] = original_1;
        };
    }
    catch (_a) {
        return function () { };
    }
}
function getWindowHeight() {
    return (window.innerHeight ||
        (document.documentElement && document.documentElement.clientHeight) ||
        (document.body && document.body.clientHeight));
}
function getWindowWidth() {
    return (window.innerWidth ||
        (document.documentElement && document.documentElement.clientWidth) ||
        (document.body && document.body.clientWidth));
}
function isBlocked(node, blockClass) {
    if (!node) {
        return false;
    }
    if (node.nodeType === node.ELEMENT_NODE) {
        var needBlock_1 = false;
        if (typeof blockClass === 'string') {
            if (node.closest !== undefined) {
                return node.closest('.' + blockClass) !== null;
            }
            else {
                needBlock_1 = node.classList.contains(blockClass);
            }
        }
        else {
            node.classList.forEach(function (className) {
                if (blockClass.test(className)) {
                    needBlock_1 = true;
                }
            });
        }
        return needBlock_1 || isBlocked(node.parentNode, blockClass);
    }
    if (node.nodeType === node.TEXT_NODE) {
        return isBlocked(node.parentNode, blockClass);
    }
    return isBlocked(node.parentNode, blockClass);
}
function isIgnored(n) {
    if ('__sn' in n) {
        return n.__sn.id === rrwebSnapshot.IGNORED_NODE;
    }
    return false;
}
function isAncestorRemoved(target, mirror) {
    if (rrwebSnapshot.isShadowRoot(target)) {
        return false;
    }
    var id = mirror.getId(target);
    if (!mirror.has(id)) {
        return true;
    }
    if (target.parentNode &&
        target.parentNode.nodeType === target.DOCUMENT_NODE) {
        return false;
    }
    if (!target.parentNode) {
        return true;
    }
    return isAncestorRemoved(target.parentNode, mirror);
}
function isTouchEvent(event) {
    return Boolean(event.changedTouches);
}
function polyfill(win) {
    if (win === void 0) { win = window; }
    if ('NodeList' in win && !win.NodeList.prototype.forEach) {
        win.NodeList.prototype.forEach = Array.prototype
            .forEach;
    }
    if ('DOMTokenList' in win && !win.DOMTokenList.prototype.forEach) {
        win.DOMTokenList.prototype.forEach = Array.prototype
            .forEach;
    }
    if (!Node.prototype.contains) {
        Node.prototype.contains = function contains(node) {
            if (!(0 in arguments)) {
                throw new TypeError('1 argument is required');
            }
            do {
                if (this === node) {
                    return true;
                }
            } while ((node = node && node.parentNode));
            return false;
        };
    }
}
var TreeIndex = (function () {
    function TreeIndex() {
        this.reset();
    }
    TreeIndex.prototype.add = function (mutation) {
        var parentTreeNode = this.indexes.get(mutation.parentId);
        var treeNode = {
            id: mutation.node.id,
            mutation: mutation,
            children: [],
            texts: [],
            attributes: [],
        };
        if (!parentTreeNode) {
            this.tree[treeNode.id] = treeNode;
        }
        else {
            treeNode.parent = parentTreeNode;
            parentTreeNode.children[treeNode.id] = treeNode;
        }
        this.indexes.set(treeNode.id, treeNode);
    };
    TreeIndex.prototype.remove = function (mutation, mirror) {
        var _this = this;
        var parentTreeNode = this.indexes.get(mutation.parentId);
        var treeNode = this.indexes.get(mutation.id);
        var deepRemoveFromMirror = function (id) {
            _this.removeIdSet.add(id);
            var node = mirror.getNode(id);
            node === null || node === void 0 ? void 0 : node.childNodes.forEach(function (childNode) {
                if ('__sn' in childNode) {
                    deepRemoveFromMirror(childNode.__sn.id);
                }
            });
        };
        var deepRemoveFromTreeIndex = function (node) {
            _this.removeIdSet.add(node.id);
            Object.values(node.children).forEach(function (n) { return deepRemoveFromTreeIndex(n); });
            var _treeNode = _this.indexes.get(node.id);
            if (_treeNode) {
                var _parentTreeNode = _treeNode.parent;
                if (_parentTreeNode) {
                    delete _treeNode.parent;
                    delete _parentTreeNode.children[_treeNode.id];
                    _this.indexes.delete(mutation.id);
                }
            }
        };
        if (!treeNode) {
            this.removeNodeMutations.push(mutation);
            deepRemoveFromMirror(mutation.id);
        }
        else if (!parentTreeNode) {
            delete this.tree[treeNode.id];
            this.indexes.delete(treeNode.id);
            deepRemoveFromTreeIndex(treeNode);
        }
        else {
            delete treeNode.parent;
            delete parentTreeNode.children[treeNode.id];
            this.indexes.delete(mutation.id);
            deepRemoveFromTreeIndex(treeNode);
        }
    };
    TreeIndex.prototype.text = function (mutation) {
        var treeNode = this.indexes.get(mutation.id);
        if (treeNode) {
            treeNode.texts.push(mutation);
        }
        else {
            this.textMutations.push(mutation);
        }
    };
    TreeIndex.prototype.attribute = function (mutation) {
        var treeNode = this.indexes.get(mutation.id);
        if (treeNode) {
            treeNode.attributes.push(mutation);
        }
        else {
            this.attributeMutations.push(mutation);
        }
    };
    TreeIndex.prototype.scroll = function (d) {
        this.scrollMap.set(d.id, d);
    };
    TreeIndex.prototype.input = function (d) {
        this.inputMap.set(d.id, d);
    };
    TreeIndex.prototype.flush = function () {
        var e_1, _a, e_2, _b;
        var _this = this;
        var _c = this, tree = _c.tree, removeNodeMutations = _c.removeNodeMutations, textMutations = _c.textMutations, attributeMutations = _c.attributeMutations;
        var batchMutationData = {
            source: types.IncrementalSource.Mutation,
            removes: removeNodeMutations,
            texts: textMutations,
            attributes: attributeMutations,
            adds: [],
        };
        var walk = function (treeNode, removed) {
            if (removed) {
                _this.removeIdSet.add(treeNode.id);
            }
            batchMutationData.texts = batchMutationData.texts
                .concat(removed ? [] : treeNode.texts)
                .filter(function (m) { return !_this.removeIdSet.has(m.id); });
            batchMutationData.attributes = batchMutationData.attributes
                .concat(removed ? [] : treeNode.attributes)
                .filter(function (m) { return !_this.removeIdSet.has(m.id); });
            if (!_this.removeIdSet.has(treeNode.id) &&
                !_this.removeIdSet.has(treeNode.mutation.parentId) &&
                !removed) {
                batchMutationData.adds.push(treeNode.mutation);
                if (treeNode.children) {
                    Object.values(treeNode.children).forEach(function (n) { return walk(n, false); });
                }
            }
            else {
                Object.values(treeNode.children).forEach(function (n) { return walk(n, true); });
            }
        };
        Object.values(tree).forEach(function (n) { return walk(n, false); });
        try {
            for (var _d = tslib_es6.__values(this.scrollMap.keys()), _e = _d.next(); !_e.done; _e = _d.next()) {
                var id = _e.value;
                if (this.removeIdSet.has(id)) {
                    this.scrollMap.delete(id);
                }
            }
        }
        catch (e_1_1) { e_1 = { error: e_1_1 }; }
        finally {
            try {
                if (_e && !_e.done && (_a = _d.return)) _a.call(_d);
            }
            finally { if (e_1) throw e_1.error; }
        }
        try {
            for (var _f = tslib_es6.__values(this.inputMap.keys()), _g = _f.next(); !_g.done; _g = _f.next()) {
                var id = _g.value;
                if (this.removeIdSet.has(id)) {
                    this.inputMap.delete(id);
                }
            }
        }
        catch (e_2_1) { e_2 = { error: e_2_1 }; }
        finally {
            try {
                if (_g && !_g.done && (_b = _f.return)) _b.call(_f);
            }
            finally { if (e_2) throw e_2.error; }
        }
        var scrollMap = new Map(this.scrollMap);
        var inputMap = new Map(this.inputMap);
        this.reset();
        return {
            mutationData: batchMutationData,
            scrollMap: scrollMap,
            inputMap: inputMap,
        };
    };
    TreeIndex.prototype.reset = function () {
        this.tree = [];
        this.indexes = new Map();
        this.removeNodeMutations = [];
        this.textMutations = [];
        this.attributeMutations = [];
        this.removeIdSet = new Set();
        this.scrollMap = new Map();
        this.inputMap = new Map();
    };
    TreeIndex.prototype.idRemoved = function (id) {
        return this.removeIdSet.has(id);
    };
    return TreeIndex;
}());
function queueToResolveTrees(queue) {
    var e_3, _a;
    var queueNodeMap = {};
    var putIntoMap = function (m, parent) {
        var nodeInTree = {
            value: m,
            parent: parent,
            children: [],
        };
        queueNodeMap[m.node.id] = nodeInTree;
        return nodeInTree;
    };
    var queueNodeTrees = [];
    try {
        for (var queue_1 = tslib_es6.__values(queue), queue_1_1 = queue_1.next(); !queue_1_1.done; queue_1_1 = queue_1.next()) {
            var mutation = queue_1_1.value;
            var nextId = mutation.nextId, parentId = mutation.parentId;
            if (nextId && nextId in queueNodeMap) {
                var nextInTree = queueNodeMap[nextId];
                if (nextInTree.parent) {
                    var idx = nextInTree.parent.children.indexOf(nextInTree);
                    nextInTree.parent.children.splice(idx, 0, putIntoMap(mutation, nextInTree.parent));
                }
                else {
                    var idx = queueNodeTrees.indexOf(nextInTree);
                    queueNodeTrees.splice(idx, 0, putIntoMap(mutation, null));
                }
                continue;
            }
            if (parentId in queueNodeMap) {
                var parentInTree = queueNodeMap[parentId];
                parentInTree.children.push(putIntoMap(mutation, parentInTree));
                continue;
            }
            queueNodeTrees.push(putIntoMap(mutation, null));
        }
    }
    catch (e_3_1) { e_3 = { error: e_3_1 }; }
    finally {
        try {
            if (queue_1_1 && !queue_1_1.done && (_a = queue_1.return)) _a.call(queue_1);
        }
        finally { if (e_3) throw e_3.error; }
    }
    return queueNodeTrees;
}
function iterateResolveTree(tree, cb) {
    cb(tree.value);
    for (var i = tree.children.length - 1; i >= 0; i--) {
        iterateResolveTree(tree.children[i], cb);
    }
}
function isIframeINode(node) {
    if ('__sn' in node) {
        return (node.__sn.type === rrwebSnapshot.NodeType.Element && node.__sn.tagName === 'iframe');
    }
    return false;
}
function getBaseDimension(node, rootIframe) {
    var _a, _b;
    var frameElement = (_b = (_a = node.ownerDocument) === null || _a === void 0 ? void 0 : _a.defaultView) === null || _b === void 0 ? void 0 : _b.frameElement;
    if (!frameElement || frameElement === rootIframe) {
        return {
            x: 0,
            y: 0,
            relativeScale: 1,
            absoluteScale: 1,
        };
    }
    var frameDimension = frameElement.getBoundingClientRect();
    var frameBaseDimension = getBaseDimension(frameElement, rootIframe);
    var relativeScale = frameDimension.height / frameElement.clientHeight;
    return {
        x: frameDimension.x * frameBaseDimension.relativeScale +
            frameBaseDimension.x,
        y: frameDimension.y * frameBaseDimension.relativeScale +
            frameBaseDimension.y,
        relativeScale: relativeScale,
        absoluteScale: frameBaseDimension.absoluteScale * relativeScale,
    };
}
function hasShadowRoot(n) {
    return Boolean(n === null || n === void 0 ? void 0 : n.shadowRoot);
}

exports.TreeIndex = TreeIndex;
exports.createMirror = createMirror;
exports.getBaseDimension = getBaseDimension;
exports.getWindowHeight = getWindowHeight;
exports.getWindowWidth = getWindowWidth;
exports.hasShadowRoot = hasShadowRoot;
exports.hookSetter = hookSetter;
exports.isAncestorRemoved = isAncestorRemoved;
exports.isBlocked = isBlocked;
exports.isIframeINode = isIframeINode;
exports.isIgnored = isIgnored;
exports.isTouchEvent = isTouchEvent;
exports.iterateResolveTree = iterateResolveTree;
exports.on = on;
exports.patch = patch;
exports.polyfill = polyfill;
exports.queueToResolveTrees = queueToResolveTrees;
exports.throttle = throttle;


},{"../../rrweb-snapshot/es/rrweb-snapshot.js":54,"../ext/tslib/tslib.es6.js":55,"./types.js":84}],86:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const index = require('./node_modules/lodash.debounce/index.js');
require('./node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js');
const constants = require('./constants.js');
const breadcrumbHandler = require('./coreHandlers/breadcrumbHandler.js');
const handleFetch = require('./coreHandlers/handleFetch.js');
const handleGlobalEvent = require('./coreHandlers/handleGlobalEvent.js');
const handleHistory = require('./coreHandlers/handleHistory.js');
const handleXhr = require('./coreHandlers/handleXhr.js');
const performanceObserver = require('./coreHandlers/performanceObserver.js');
const createPerformanceEntry = require('./createPerformanceEntry.js');
const eventBuffer = require('./eventBuffer.js');
const deleteSession = require('./session/deleteSession.js');
const getSession = require('./session/getSession.js');
const saveSession = require('./session/saveSession.js');
const addEvent = require('./util/addEvent.js');
const addMemoryEntry = require('./util/addMemoryEntry.js');
const createBreadcrumb = require('./util/createBreadcrumb.js');
const createPayload = require('./util/createPayload.js');
const createPerformanceSpans = require('./util/createPerformanceSpans.js');
const createReplayEnvelope = require('./util/createReplayEnvelope.js');
const getReplayEvent = require('./util/getReplayEvent.js');
const isExpired = require('./util/isExpired.js');
const isSessionExpired = require('./util/isSessionExpired.js');
const monkeyPatchRecordDroppedEvent = require('./util/monkeyPatchRecordDroppedEvent.js');
const index$1 = require('./node_modules/rrweb/es/rrweb/packages/rrweb/src/record/index.js');
const types = require('./node_modules/rrweb/es/rrweb/packages/rrweb/src/types.js');

/* eslint-disable max-lines */ // TODO: We might want to split this file up

/**
 * Returns true to return control to calling function, otherwise continue with normal batching
 */

const BASE_RETRY_INTERVAL = 5000;
const MAX_RETRY_COUNT = 3;

class ReplayContainer  {
   __init() {this.eventBuffer = null;}

  /**
   * List of PerformanceEntry from PerformanceObserver
   */
   __init2() {this.performanceEvents = [];}

  /**
   * Recording can happen in one of two modes:
   * * session: Record the whole session, sending it continuously
   * * error: Always keep the last 60s of recording, and when an error occurs, send it immediately
   */
   __init3() {this.recordingMode = 'session';}

  /**
   * Options to pass to `rrweb.record()`
   */

   __init4() {this._performanceObserver = null;}

   __init5() {this._retryCount = 0;}
   __init6() {this._retryInterval = BASE_RETRY_INTERVAL;}

   __init7() {this._flushLock = null;}

  /**
   * Timestamp of the last user activity. This lives across sessions.
   */
   __init8() {this._lastActivity = new Date().getTime();}

  /**
   * Is the integration currently active?
   */
   __init9() {this._isEnabled = false;}

  /**
   * Paused is a state where:
   * - DOM Recording is not listening at all
   * - Nothing will be added to event buffer (e.g. core SDK events)
   */
   __init10() {this._isPaused = false;}

  /**
   * Have we attached listeners to the core SDK?
   * Note we have to track this as there is no way to remove instrumentation handlers.
   */
   __init11() {this._hasInitializedCoreListeners = false;}

  /**
   * Function to stop recording
   */
   __init12() {this._stopRecording = null;}

   __init13() {this._context = {
    errorIds: new Set(),
    traceIds: new Set(),
    urls: [],
    earliestEvent: null,
    initialTimestamp: new Date().getTime(),
    initialUrl: '',
  };}

  constructor({ options, recordingOptions }) {;ReplayContainer.prototype.__init.call(this);ReplayContainer.prototype.__init2.call(this);ReplayContainer.prototype.__init3.call(this);ReplayContainer.prototype.__init4.call(this);ReplayContainer.prototype.__init5.call(this);ReplayContainer.prototype.__init6.call(this);ReplayContainer.prototype.__init7.call(this);ReplayContainer.prototype.__init8.call(this);ReplayContainer.prototype.__init9.call(this);ReplayContainer.prototype.__init10.call(this);ReplayContainer.prototype.__init11.call(this);ReplayContainer.prototype.__init12.call(this);ReplayContainer.prototype.__init13.call(this);ReplayContainer.prototype.__init14.call(this);ReplayContainer.prototype.__init15.call(this);ReplayContainer.prototype.__init16.call(this);ReplayContainer.prototype.__init17.call(this);ReplayContainer.prototype.__init18.call(this);ReplayContainer.prototype.__init19.call(this);
    this._recordingOptions = recordingOptions;
    this._options = options;

    this._debouncedFlush = index.default(() => this.flush(), this._options.flushMinDelay, {
      maxWait: this._options.flushMaxDelay,
    });
  }

  /** Get the event context. */
   getContext() {
    return this._context;
  }

  /** If recording is currently enabled. */
   isEnabled() {
    return this._isEnabled;
  }

  /** If recording is currently paused. */
   isPaused() {
    return this._isPaused;
  }

  /** Get the replay integration options. */
   getOptions() {
    return this._options;
  }

  /**
   * Initializes the plugin.
   *
   * Creates or loads a session, attaches listeners to varying events (DOM,
   * _performanceObserver, Recording, Sentry SDK, etc)
   */
  start() {
    this.setInitialState();

    this.loadSession({ expiry: constants.SESSION_IDLE_DURATION });

    // If there is no session, then something bad has happened - can't continue
    if (!this.session) {
      this.handleException(new Error('No session found'));
      return;
    }

    if (!this.session.sampled) {
      // If session was not sampled, then we do not initialize the integration at all.
      return;
    }

    // Modify recording options to checkoutEveryNthSecond if
    // sampling for error replay. This is because we don't know
    // when an error will occur, so we need to keep a buffer of
    // replay events.
    if (this.session.sampled === 'error') {
      this.recordingMode = 'error';
    }

    // setup() is generally called on page load or manually - in both cases we
    // should treat it as an activity
    this.updateSessionActivity();

    this.eventBuffer = eventBuffer.createEventBuffer({
      useCompression: Boolean(this._options.useCompression),
    });

    this.addListeners();

    // Need to set as enabled before we start recording, as `record()` can trigger a flush with a new checkout
    this._isEnabled = true;

    this.startRecording();
  }

  /**
   * Start recording.
   *
   * Note that this will cause a new DOM checkout
   */
  startRecording() {
    try {
      this._stopRecording = index$1.default({
        ...this._recordingOptions,
        // When running in error sampling mode, we need to overwrite `checkoutEveryNth`
        // Without this, it would record forever, until an error happens, which we don't want
        // instead, we'll always keep the last 60 seconds of replay before an error happened
        ...(this.recordingMode === 'error' && { checkoutEveryNth: 60000 }),
        emit: this.handleRecordingEmit,
      });
    } catch (err) {
      this.handleException(err);
    }
  }

  /**
   * Stops the recording, if it was running.
   * Returns true if it was stopped, else false.
   */
   stopRecording() {
    if (this._stopRecording) {
      this._stopRecording();
      return true;
    }

    return false;
  }

  /**
   * Currently, this needs to be manually called (e.g. for tests). Sentry SDK
   * does not support a teardown
   */
  stop() {
    try {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Stopping Replays');
      this._isEnabled = false;
      this.removeListeners();
      _optionalChain([this, 'access', _8 => _8._stopRecording, 'optionalCall', _9 => _9()]);
      _optionalChain([this, 'access', _10 => _10.eventBuffer, 'optionalAccess', _11 => _11.destroy, 'call', _12 => _12()]);
      this.eventBuffer = null;
    } catch (err) {
      this.handleException(err);
    }
  }

  /**
   * Pause some replay functionality. See comments for `_isPaused`.
   * This differs from stop as this only stops DOM recording, it is
   * not as thorough of a shutdown as `stop()`.
   */
  pause() {
    this._isPaused = true;
    try {
      if (this._stopRecording) {
        this._stopRecording();
        this._stopRecording = undefined;
      }
    } catch (err) {
      this.handleException(err);
    }
  }

  /**
   * Resumes recording, see notes for `pause().
   *
   * Note that calling `startRecording()` here will cause a
   * new DOM checkout.`
   */
  resume() {
    this._isPaused = false;
    this.startRecording();
  }

  /** A wrapper to conditionally capture exceptions. */
  handleException(error) {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('[Replay]', error);

    if ((typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && this._options._experiments && this._options._experiments.captureExceptions) {
      core.captureException(error);
    }
  }

  /** for tests only */
  clearSession() {
    try {
      deleteSession.deleteSession();
      this.session = undefined;
    } catch (err) {
      this.handleException(err);
    }
  }

  /**
   * Loads a session from storage, or creates a new one if it does not exist or
   * is expired.
   */
  loadSession({ expiry }) {
    const { type, session } = getSession.getSession({
      expiry,
      stickySession: Boolean(this._options.stickySession),
      currentSession: this.session,
      sessionSampleRate: this._options.sessionSampleRate,
      errorSampleRate: this._options.errorSampleRate,
    });

    // If session was newly created (i.e. was not loaded from storage), then
    // enable flag to create the root replay
    if (type === 'new') {
      this.setInitialState();
    }

    if (session.id !== _optionalChain([this, 'access', _13 => _13.session, 'optionalAccess', _14 => _14.id])) {
      session.previousSessionId = _optionalChain([this, 'access', _15 => _15.session, 'optionalAccess', _16 => _16.id]);
    }

    this.session = session;
  }

  /**
   * Capture some initial state that can change throughout the lifespan of the
   * replay. This is required because otherwise they would be captured at the
   * first flush.
   */
  setInitialState() {
    const urlPath = `${constants.WINDOW.location.pathname}${constants.WINDOW.location.hash}${constants.WINDOW.location.search}`;
    const url = `${constants.WINDOW.location.origin}${urlPath}`;

    this.performanceEvents = [];

    // Reset _context as well
    this.clearContext();

    this._context.initialUrl = url;
    this._context.initialTimestamp = new Date().getTime();
    this._context.urls.push(url);
  }

  /**
   * Adds listeners to record events for the replay
   */
  addListeners() {
    try {
      constants.WINDOW.document.addEventListener('visibilitychange', this.handleVisibilityChange);
      constants.WINDOW.addEventListener('blur', this.handleWindowBlur);
      constants.WINDOW.addEventListener('focus', this.handleWindowFocus);

      // We need to filter out dropped events captured by `addGlobalEventProcessor(this.handleGlobalEvent)` below
      monkeyPatchRecordDroppedEvent.overwriteRecordDroppedEvent(this._context.errorIds);

      // There is no way to remove these listeners, so ensure they are only added once
      if (!this._hasInitializedCoreListeners) {
        // Listeners from core SDK //
        const scope = core.getCurrentHub().getScope();
        _optionalChain([scope, 'optionalAccess', _17 => _17.addScopeListener, 'call', _18 => _18(this.handleCoreBreadcrumbListener('scope'))]);
        utils.addInstrumentationHandler('dom', this.handleCoreBreadcrumbListener('dom'));
        utils.addInstrumentationHandler('fetch', handleFetch.handleFetchSpanListener(this));
        utils.addInstrumentationHandler('xhr', handleXhr.handleXhrSpanListener(this));
        utils.addInstrumentationHandler('history', handleHistory.handleHistorySpanListener(this));

        // Tag all (non replay) events that get sent to Sentry with the current
        // replay ID so that we can reference them later in the UI
        core.addGlobalEventProcessor(handleGlobalEvent.handleGlobalEventListener(this));

        this._hasInitializedCoreListeners = true;
      }
    } catch (err) {
      this.handleException(err);
    }

    // _performanceObserver //
    if (!('_performanceObserver' in constants.WINDOW)) {
      return;
    }

    this._performanceObserver = performanceObserver.setupPerformanceObserver(this);
  }

  /**
   * Cleans up listeners that were created in `addListeners`
   */
  removeListeners() {
    try {
      constants.WINDOW.document.removeEventListener('visibilitychange', this.handleVisibilityChange);

      constants.WINDOW.removeEventListener('blur', this.handleWindowBlur);
      constants.WINDOW.removeEventListener('focus', this.handleWindowFocus);

      monkeyPatchRecordDroppedEvent.restoreRecordDroppedEvent();

      if (this._performanceObserver) {
        this._performanceObserver.disconnect();
        this._performanceObserver = null;
      }
    } catch (err) {
      this.handleException(err);
    }
  }

  /**
   * We want to batch uploads of replay events. Save events only if
   * `<flushMinDelay>` milliseconds have elapsed since the last event
   * *OR* if `<flushMaxDelay>` milliseconds have elapsed.
   *
   * Accepts a callback to perform side-effects and returns true to stop batch
   * processing and hand back control to caller.
   */
  addUpdate(cb) {
    // We need to always run `cb` (e.g. in the case of `this.recordingMode == 'error'`)
    const cbResult = _optionalChain([cb, 'optionalCall', _19 => _19()]);

    // If this option is turned on then we will only want to call `flush`
    // explicitly
    if (this.recordingMode === 'error') {
      return;
    }

    // If callback is true, we do not want to continue with flushing -- the
    // caller will need to handle it.
    if (cbResult === true) {
      return;
    }

    // addUpdate is called quite frequently - use _debouncedFlush so that it
    // respects the flush delays and does not flush immediately
    this._debouncedFlush();
  }

  /**
   * Handler for recording events.
   *
   * Adds to event buffer, and has varying flushing behaviors if the event was a checkout.
   */
  __init14() {this.handleRecordingEmit = (
    event,
    isCheckout,
  ) => {
    // If this is false, it means session is expired, create and a new session and wait for checkout
    if (!this.checkAndHandleExpiredSession()) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('[Replay] Received replay event after session expired.');

      return;
    }

    this.addUpdate(() => {
      // The session is always started immediately on pageload/init, but for
      // error-only replays, it should reflect the most recent checkout
      // when an error occurs. Clear any state that happens before this current
      // checkout. This needs to happen before `addEvent()` which updates state
      // dependent on this reset.
      if (this.recordingMode === 'error' && event.type === 2) {
        this.setInitialState();
      }

      // We need to clear existing events on a checkout, otherwise they are
      // incremental event updates and should be appended
      addEvent.addEvent(this, event, isCheckout);

      // Different behavior for full snapshots (type=2), ignore other event types
      // See https://github.com/rrweb-io/rrweb/blob/d8f9290ca496712aa1e7d472549480c4e7876594/packages/rrweb/src/types.ts#L16
      if (event.type !== 2) {
        return false;
      }

      // If there is a previousSessionId after a full snapshot occurs, then
      // the replay session was started due to session expiration. The new session
      // is started before triggering a new checkout and contains the id
      // of the previous session. Do not immediately flush in this case
      // to avoid capturing only the checkout and instead the replay will
      // be captured if they perform any follow-up actions.
      if (_optionalChain([this, 'access', _20 => _20.session, 'optionalAccess', _21 => _21.previousSessionId])) {
        return true;
      }

      // See note above re: session start needs to reflect the most recent
      // checkout.
      if (this.recordingMode === 'error' && this.session && this._context.earliestEvent) {
        this.session.started = this._context.earliestEvent;
        this._maybeSaveSession();
      }

      // Flush immediately so that we do not miss the first segment, otherwise
      // it can prevent loading on the UI. This will cause an increase in short
      // replays (e.g. opening and closing a tab quickly), but these can be
      // filtered on the UI.
      if (this.recordingMode === 'session') {
        void this.flushImmediate();
      }

      return true;
    });
  };}

  /**
   * Handle when visibility of the page content changes. Opening a new tab will
   * cause the state to change to hidden because of content of current page will
   * be hidden. Likewise, moving a different window to cover the contents of the
   * page will also trigger a change to a hidden state.
   */
  __init15() {this.handleVisibilityChange = () => {
    if (constants.WINDOW.document.visibilityState === 'visible') {
      this.doChangeToForegroundTasks();
    } else {
      this.doChangeToBackgroundTasks();
    }
  };}

  /**
   * Handle when page is blurred
   */
  __init16() {this.handleWindowBlur = () => {
    const breadcrumb = createBreadcrumb.createBreadcrumb({
      category: 'ui.blur',
    });

    // Do not count blur as a user action -- it's part of the process of them
    // leaving the page
    this.doChangeToBackgroundTasks(breadcrumb);
  };}

  /**
   * Handle when page is focused
   */
  __init17() {this.handleWindowFocus = () => {
    const breadcrumb = createBreadcrumb.createBreadcrumb({
      category: 'ui.focus',
    });

    // Do not count focus as a user action -- instead wait until they focus and
    // interactive with page
    this.doChangeToForegroundTasks(breadcrumb);
  };}

  /**
   * Handler for Sentry Core SDK events.
   *
   * These events will create breadcrumb-like objects in the recording.
   */
  __init18() {this.handleCoreBreadcrumbListener =
    (type) =>
    (handlerData) => {
      if (!this._isEnabled) {
        return;
      }

      const result = breadcrumbHandler.breadcrumbHandler(type, handlerData);

      if (result === null) {
        return;
      }

      if (result.category === 'sentry.transaction') {
        return;
      }

      if (result.category === 'ui.click') {
        this.triggerUserActivity();
      } else {
        this.checkAndHandleExpiredSession();
      }

      this.addUpdate(() => {
        addEvent.addEvent(this, {
          type: types.EventType.Custom,
          // TODO: We were converting from ms to seconds for breadcrumbs, spans,
          // but maybe we should just keep them as milliseconds
          timestamp: (result.timestamp || 0) * 1000,
          data: {
            tag: 'breadcrumb',
            payload: result,
          },
        });

        // Do not flush after console log messages
        return result.category === 'console';
      });
    };}

  /**
   * Tasks to run when we consider a page to be hidden (via blurring and/or visibility)
   */
  doChangeToBackgroundTasks(breadcrumb) {
    if (!this.session) {
      return;
    }

    const expired = isSessionExpired.isSessionExpired(this.session, constants.VISIBILITY_CHANGE_TIMEOUT);

    if (breadcrumb && !expired) {
      this.createCustomBreadcrumb(breadcrumb);
    }

    // Send replay when the page/tab becomes hidden. There is no reason to send
    // replay if it becomes visible, since no actions we care about were done
    // while it was hidden
    this.conditionalFlush();
  }

  /**
   * Tasks to run when we consider a page to be visible (via focus and/or visibility)
   */
  doChangeToForegroundTasks(breadcrumb) {
    if (!this.session) {
      return;
    }

    const isSessionActive = this.checkAndHandleExpiredSession({
      expiry: constants.VISIBILITY_CHANGE_TIMEOUT,
    });

    if (!isSessionActive) {
      // If the user has come back to the page within VISIBILITY_CHANGE_TIMEOUT
      // ms, we will re-use the existing session, otherwise create a new
      // session
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Document has become active, but session has expired');
      return;
    }

    if (breadcrumb) {
      this.createCustomBreadcrumb(breadcrumb);
    }
  }

  /**
   * Trigger rrweb to take a full snapshot which will cause this plugin to
   * create a new Replay event.
   */
  triggerFullSnapshot() {
    (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Taking full rrweb snapshot');
    index$1.default.takeFullSnapshot(true);
  }

  /**
   * Update user activity (across session lifespans)
   */
  updateUserActivity(_lastActivity = new Date().getTime()) {
    this._lastActivity = _lastActivity;
  }

  /**
   * Updates the session's last activity timestamp
   */
  updateSessionActivity(_lastActivity = new Date().getTime()) {
    if (this.session) {
      this.session.lastActivity = _lastActivity;
      this._maybeSaveSession();
    }
  }

  /**
   * Updates the user activity timestamp and resumes recording. This should be
   * called in an event handler for a user action that we consider as the user
   * being "active" (e.g. a mouse click).
   */
  triggerUserActivity() {
    this.updateUserActivity();

    // This case means that recording was once stopped due to inactivity.
    // Ensure that recording is resumed.
    if (!this._stopRecording) {
      // Create a new session, otherwise when the user action is flushed, it
      // will get rejected due to an expired session.
      this.loadSession({ expiry: constants.SESSION_IDLE_DURATION });

      // Note: This will cause a new DOM checkout
      this.resume();
      return;
    }

    // Otherwise... recording was never suspended, continue as normalish
    this.checkAndHandleExpiredSession();

    this.updateSessionActivity();
  }

  /**
   * Helper to create (and buffer) a replay breadcrumb from a core SDK breadcrumb
   */
  createCustomBreadcrumb(breadcrumb) {
    this.addUpdate(() => {
      addEvent.addEvent(this, {
        type: types.EventType.Custom,
        timestamp: breadcrumb.timestamp || 0,
        data: {
          tag: 'breadcrumb',
          payload: breadcrumb,
        },
      });
    });
  }

  /**
   * Observed performance events are added to `this.performanceEvents`. These
   * are included in the replay event before it is finished and sent to Sentry.
   */
  addPerformanceEntries() {
    // Copy and reset entries before processing
    const entries = [...this.performanceEvents];
    this.performanceEvents = [];

    createPerformanceSpans.createPerformanceSpans(this, createPerformanceEntry.createPerformanceEntries(entries));
  }

  /**
   * Checks if recording should be stopped due to user inactivity. Otherwise
   * check if session is expired and create a new session if so. Triggers a new
   * full snapshot on new session.
   *
   * Returns true if session is not expired, false otherwise.
   */
  checkAndHandleExpiredSession({ expiry = constants.SESSION_IDLE_DURATION } = {}) {
    const oldSessionId = _optionalChain([this, 'access', _22 => _22.session, 'optionalAccess', _23 => _23.id]);

    // Prevent starting a new session if the last user activity is older than
    // MAX_SESSION_LIFE. Otherwise non-user activity can trigger a new
    // session+recording. This creates noisy replays that do not have much
    // content in them.
    if (this._lastActivity && isExpired.isExpired(this._lastActivity, constants.MAX_SESSION_LIFE)) {
      // Pause recording
      this.pause();
      return;
    }

    // --- There is recent user activity --- //
    // This will create a new session if expired, based on expiry length
    this.loadSession({ expiry });

    // Session was expired if session ids do not match
    const expired = oldSessionId !== _optionalChain([this, 'access', _24 => _24.session, 'optionalAccess', _25 => _25.id]);

    if (!expired) {
      return true;
    }

    // Session is expired, trigger a full snapshot (which will create a new session)
    this.triggerFullSnapshot();

    return false;
  }

  /**
   * Only flush if `this.recordingMode === 'session'`
   */
  conditionalFlush() {
    if (this.recordingMode === 'error') {
      return;
    }

    void this.flushImmediate();
  }

  /**
   * Clear _context
   */
  clearContext() {
    // XXX: `initialTimestamp` and `initialUrl` do not get cleared
    this._context.errorIds.clear();
    this._context.traceIds.clear();
    this._context.urls = [];
    this._context.earliestEvent = null;
  }

  /**
   * Return and clear _context
   */
  popEventContext() {
    if (this._context.earliestEvent && this._context.earliestEvent < this._context.initialTimestamp) {
      this._context.initialTimestamp = this._context.earliestEvent;
    }

    const _context = {
      initialTimestamp: this._context.initialTimestamp,
      initialUrl: this._context.initialUrl,
      errorIds: Array.from(this._context.errorIds).filter(Boolean),
      traceIds: Array.from(this._context.traceIds).filter(Boolean),
      urls: this._context.urls,
    };

    this.clearContext();

    return _context;
  }

  /**
   * Flushes replay event buffer to Sentry.
   *
   * Performance events are only added right before flushing - this is
   * due to the buffered performance observer events.
   *
   * Should never be called directly, only by `flush`
   */
  async runFlush() {
    if (!this.session) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('[Replay] No session found to flush.');
      return;
    }

    await this.addPerformanceEntries();

    if (!_optionalChain([this, 'access', _26 => _26.eventBuffer, 'optionalAccess', _27 => _27.length])) {
      return;
    }

    // Only attach memory event if eventBuffer is not empty
    await addMemoryEntry.addMemoryEntry(this);

    try {
      // Note this empties the event buffer regardless of outcome of sending replay
      const recordingData = await this.eventBuffer.finish();

      // NOTE: Copy values from instance members, as it's possible they could
      // change before the flush finishes.
      const replayId = this.session.id;
      const eventContext = this.popEventContext();
      // Always increment segmentId regardless of outcome of sending replay
      const segmentId = this.session.segmentId++;
      this._maybeSaveSession();

      await this.sendReplay({
        replayId,
        events: recordingData,
        segmentId,
        includeReplayStartTimestamp: segmentId === 0,
        eventContext,
      });
    } catch (err) {
      this.handleException(err);
    }
  }

  /**
   * Flush recording data to Sentry. Creates a lock so that only a single flush
   * can be active at a time. Do not call this directly.
   */
  __init19() {this.flush = async () => {
    if (!this._isEnabled) {
      // This is just a precaution, there should be no listeners that would
      // cause a flush.
      return;
    }

    if (!this.checkAndHandleExpiredSession()) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('[Replay] Attempting to finish replay event after session expired.');
      return;
    }

    if (!_optionalChain([this, 'access', _28 => _28.session, 'optionalAccess', _29 => _29.id])) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error('[Replay] No session found to flush.');
      return;
    }

    // A flush is about to happen, cancel any queued flushes
    _optionalChain([this, 'access', _30 => _30._debouncedFlush, 'optionalAccess', _31 => _31.cancel, 'call', _32 => _32()]);

    // No existing flush in progress, proceed with flushing.
    // this._flushLock acts as a lock so that future calls to `flush()`
    // will be blocked until this promise resolves
    if (!this._flushLock) {
      this._flushLock = this.runFlush();
      await this._flushLock;
      this._flushLock = null;
      return;
    }

    // Wait for previous flush to finish, then call the debounced `flush()`.
    // It's possible there are other flush requests queued and waiting for it
    // to resolve. We want to reduce all outstanding requests (as well as any
    // new flush requests that occur within a second of the locked flush
    // completing) into a single flush.

    try {
      await this._flushLock;
    } catch (err) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.error(err);
    } finally {
      this._debouncedFlush();
    }
  };}

  /**
   *
   * Always flush via `_debouncedFlush` so that we do not have flushes triggered
   * from calling both `flush` and `_debouncedFlush`. Otherwise, there could be
   * cases of mulitple flushes happening closely together.
   */
  flushImmediate() {
    this._debouncedFlush();
    // `.flush` is provided by lodash.debounce
    return this._debouncedFlush.flush();
  }

  /**
   * Send replay attachment using `fetch()`
   */
  async sendReplayRequest({
    events,
    replayId,
    segmentId: segment_id,
    includeReplayStartTimestamp,
    eventContext,
  }) {
    const payloadWithSequence = createPayload.createPayload({
      events,
      headers: {
        segment_id,
      },
    });

    const { urls, errorIds, traceIds, initialTimestamp } = eventContext;

    const currentTimestamp = new Date().getTime();

    const hub = core.getCurrentHub();
    const client = hub.getClient();
    const scope = hub.getScope();
    const transport = client && client.getTransport();
    const dsn = _optionalChain([client, 'optionalAccess', _33 => _33.getDsn, 'call', _34 => _34()]);

    if (!client || !scope || !transport || !dsn) {
      return;
    }

    const baseEvent = {
      // @ts-ignore private api
      type: constants.REPLAY_EVENT_NAME,
      ...(includeReplayStartTimestamp ? { replay_start_timestamp: initialTimestamp / 1000 } : {}),
      timestamp: currentTimestamp / 1000,
      error_ids: errorIds,
      trace_ids: traceIds,
      urls,
      replay_id: replayId,
      segment_id,
    };

    const replayEvent = await getReplayEvent.getReplayEvent({ scope, client, replayId, event: baseEvent });
    replayEvent.tags = {
      ...replayEvent.tags,
      sessionSampleRate: this._options.sessionSampleRate,
      errorSampleRate: this._options.errorSampleRate,
      replayType: _optionalChain([this, 'access', _35 => _35.session, 'optionalAccess', _36 => _36.sampled]),
    };

    /*
    For reference, the fully built event looks something like this:
    {
        "type": "replay_event",
        "timestamp": 1670837008.634,
        "error_ids": [
            "errorId"
        ],
        "trace_ids": [
            "traceId"
        ],
        "urls": [
            "https://example.com"
        ],
        "replay_id": "eventId",
        "segment_id": 3,
        "platform": "javascript",
        "event_id": "eventId",
        "environment": "production",
        "sdk": {
            "integrations": [
                "BrowserTracing",
                "Replay"
            ],
            "name": "sentry.javascript.browser",
            "version": "7.25.0"
        },
        "sdkProcessingMetadata": {},
        "tags": {
            "sessionSampleRate": 1,
            "errorSampleRate": 0,
            "replayType": "error"
        }
    }
    */

    const envelope = createReplayEnvelope.createReplayEnvelope(replayEvent, payloadWithSequence, dsn, client.getOptions().tunnel);

    try {
      return transport.send(envelope);
    } catch (e) {
      throw new Error(constants.UNABLE_TO_SEND_REPLAY);
    }
  }

  resetRetries() {
    this._retryCount = 0;
    this._retryInterval = BASE_RETRY_INTERVAL;
  }

  /**
   * Finalize and send the current replay event to Sentry
   */
  async sendReplay({
    replayId,
    events,
    segmentId,
    includeReplayStartTimestamp,
    eventContext,
  }) {
    // short circuit if there's no events to upload (this shouldn't happen as runFlush makes this check)
    if (!events.length) {
      return;
    }

    try {
      await this.sendReplayRequest({
        events,
        replayId,
        segmentId,
        includeReplayStartTimestamp,
        eventContext,
      });
      this.resetRetries();
      return true;
    } catch (err) {
      // Capture error for every failed replay
      core.setContext('Replays', {
        _retryCount: this._retryCount,
      });
      this.handleException(err);

      // If an error happened here, it's likely that uploading the attachment
      // failed, we'll can retry with the same events payload
      if (this._retryCount >= MAX_RETRY_COUNT) {
        throw new Error(`${constants.UNABLE_TO_SEND_REPLAY} - max retries exceeded`);
      }

      this._retryCount = this._retryCount + 1;
      // will retry in intervals of 5, 10, 30
      this._retryInterval = this._retryCount * this._retryInterval;

      return await new Promise((resolve, reject) => {
        setTimeout(async () => {
          try {
            await this.sendReplay({
              replayId,
              events,
              segmentId,
              includeReplayStartTimestamp,
              eventContext,
            });
            resolve(true);
          } catch (err) {
            reject(err);
          }
        }, this._retryInterval);
      });
    }
  }

  /** Save the session, if it is sticky */
   _maybeSaveSession() {
    if (this.session && this._options.stickySession) {
      saveSession.saveSession(this.session);
    }
  }
}

exports.ReplayContainer = ReplayContainer;


},{"./constants.js":36,"./coreHandlers/breadcrumbHandler.js":37,"./coreHandlers/handleFetch.js":39,"./coreHandlers/handleGlobalEvent.js":40,"./coreHandlers/handleHistory.js":41,"./coreHandlers/handleXhr.js":43,"./coreHandlers/performanceObserver.js":44,"./createPerformanceEntry.js":45,"./eventBuffer.js":46,"./node_modules/lodash.debounce/index.js":49,"./node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js":56,"./node_modules/rrweb/es/rrweb/packages/rrweb/src/record/index.js":66,"./node_modules/rrweb/es/rrweb/packages/rrweb/src/types.js":84,"./session/deleteSession.js":89,"./session/getSession.js":91,"./session/saveSession.js":92,"./util/addEvent.js":93,"./util/addMemoryEntry.js":94,"./util/createBreadcrumb.js":95,"./util/createPayload.js":96,"./util/createPerformanceSpans.js":97,"./util/createReplayEnvelope.js":98,"./util/getReplayEvent.js":100,"./util/isExpired.js":102,"./util/isSessionExpired.js":105,"./util/monkeyPatchRecordDroppedEvent.js":106,"@sentry/core":24,"@sentry/utils":130,"@sentry/utils/cjs/buildPolyfills":124}],87:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const isSampled = require('../util/isSampled.js');

/**
 * Get a session with defaults & applied sampling.
 */
function makeSession(session) {
  const now = new Date().getTime();
  const id = session.id || utils.uuid4();
  // Note that this means we cannot set a started/lastActivity of `0`, but this should not be relevant outside of tests.
  const started = session.started || now;
  const lastActivity = session.lastActivity || now;
  const segmentId = session.segmentId || 0;
  const sampled = session.sampled;

  return {
    id,
    started,
    lastActivity,
    segmentId,
    sampled,
  };
}

/**
 * Get the sampled status for a session based on sample rates & current sampled status.
 */
function getSessionSampleType(sessionSampleRate, errorSampleRate) {
  return isSampled.isSampled(sessionSampleRate) ? 'session' : isSampled.isSampled(errorSampleRate) ? 'error' : false;
}

exports.getSessionSampleType = getSessionSampleType;
exports.makeSession = makeSession;


},{"../util/isSampled.js":104,"@sentry/utils":130}],88:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const saveSession = require('./saveSession.js');
const Session = require('./Session.js');

/**
 * Create a new session, which in its current implementation is a Sentry event
 * that all replays will be saved to as attachments. Currently, we only expect
 * one of these Sentry events per "replay session".
 */
function createSession({ sessionSampleRate, errorSampleRate, stickySession = false }) {
  const sampled = Session.getSessionSampleType(sessionSampleRate, errorSampleRate);
  const session = Session.makeSession({
    sampled,
  });

  (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log(`[Replay] Creating new session: ${session.id}`);

  if (stickySession) {
    saveSession.saveSession(session);
  }

  return session;
}

exports.createSession = createSession;


},{"./Session.js":87,"./saveSession.js":92,"@sentry/utils":130}],89:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const constants = require('../constants.js');

/**
 * Deletes a session from storage
 */
function deleteSession() {
  const hasSessionStorage = 'sessionStorage' in constants.WINDOW;

  if (!hasSessionStorage) {
    return;
  }

  try {
    constants.WINDOW.sessionStorage.removeItem(constants.REPLAY_SESSION_KEY);
  } catch (e) {
    // Ignore potential SecurityError exceptions
  }
}

exports.deleteSession = deleteSession;


},{"../constants.js":36}],90:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const constants = require('../constants.js');
const Session = require('./Session.js');

/**
 * Fetches a session from storage
 */
function fetchSession() {
  const hasSessionStorage = 'sessionStorage' in constants.WINDOW;

  if (!hasSessionStorage) {
    return null;
  }

  try {
    // This can throw if cookies are disabled
    const sessionStringFromStorage = constants.WINDOW.sessionStorage.getItem(constants.REPLAY_SESSION_KEY);

    if (!sessionStringFromStorage) {
      return null;
    }

    const sessionObj = JSON.parse(sessionStringFromStorage) ;

    return Session.makeSession(sessionObj);
  } catch (e) {
    return null;
  }
}

exports.fetchSession = fetchSession;


},{"../constants.js":36,"./Session.js":87}],91:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const isSessionExpired = require('../util/isSessionExpired.js');
const createSession = require('./createSession.js');
const fetchSession = require('./fetchSession.js');

/**
 * Get or create a session
 */
function getSession({
  expiry,
  currentSession,
  stickySession,
  sessionSampleRate,
  errorSampleRate,
}) {
  // If session exists and is passed, use it instead of always hitting session storage
  const session = currentSession || (stickySession && fetchSession.fetchSession());

  if (session) {
    // If there is a session, check if it is valid (e.g. "last activity" time
    // should be within the "session idle time", and "session started" time is
    // within "max session time").
    const isExpired = isSessionExpired.isSessionExpired(session, expiry);

    if (!isExpired) {
      return { type: 'saved', session };
    } else {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && utils.logger.log('[Replay] Session has expired');
    }
    // Otherwise continue to create a new session
  }

  const newSession = createSession.createSession({
    stickySession,
    sessionSampleRate,
    errorSampleRate,
  });

  return { type: 'new', session: newSession };
}

exports.getSession = getSession;


},{"../util/isSessionExpired.js":105,"./createSession.js":88,"./fetchSession.js":90,"@sentry/utils":130}],92:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const constants = require('../constants.js');

function saveSession(session) {
  const hasSessionStorage = 'sessionStorage' in constants.WINDOW;
  if (!hasSessionStorage) {
    return;
  }

  try {
    constants.WINDOW.sessionStorage.setItem(constants.REPLAY_SESSION_KEY, JSON.stringify(session));
  } catch (e) {
    // Ignore potential SecurityError exceptions
  }
}

exports.saveSession = saveSession;


},{"../constants.js":36}],93:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const constants = require('../constants.js');

/**
 * Add an event to the event buffer
 */
function addEvent(replay, event, isCheckout) {
  if (!replay.eventBuffer) {
    // This implies that `_isEnabled` is false
    return;
  }

  if (replay.isPaused()) {
    // Do not add to event buffer when recording is paused
    return;
  }

  // TODO: sadness -- we will want to normalize timestamps to be in ms -
  // requires coordination with frontend
  const isMs = event.timestamp > 9999999999;
  const timestampInMs = isMs ? event.timestamp : event.timestamp * 1000;

  // Throw out events that happen more than 5 minutes ago. This can happen if
  // page has been left open and idle for a long period of time and user
  // comes back to trigger a new session. The performance entries rely on
  // `performance.timeOrigin`, which is when the page first opened.
  if (timestampInMs + constants.SESSION_IDLE_DURATION < new Date().getTime()) {
    return;
  }

  // Only record earliest event if a new session was created, otherwise it
  // shouldn't be relevant
  const earliestEvent = replay.getContext().earliestEvent;
  if (_optionalChain([replay, 'access', _ => _.session, 'optionalAccess', _2 => _2.segmentId]) === 0 && (!earliestEvent || timestampInMs < earliestEvent)) {
    replay.getContext().earliestEvent = timestampInMs;
  }

  replay.eventBuffer.addEvent(event, isCheckout);
}

exports.addEvent = addEvent;


},{"../constants.js":36,"@sentry/utils/cjs/buildPolyfills":124}],94:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const constants = require('../constants.js');
const createPerformanceSpans = require('./createPerformanceSpans.js');

/**
 * Create a "span" for the total amount of memory being used by JS objects
 * (including v8 internal objects).
 */
function addMemoryEntry(replay) {
  // window.performance.memory is a non-standard API and doesn't work on all browsers, so we try-catch this
  try {
    createPerformanceSpans.createPerformanceSpans(replay, [
      // @ts-ignore memory doesn't exist on type Performance as the API is non-standard (we check that it exists above)
      createMemoryEntry(constants.WINDOW.performance.memory),
    ]);
  } catch (error) {
    // Do nothing
  }
}

exports.addMemoryEntry = addMemoryEntry;


},{"../constants.js":36,"./createPerformanceSpans.js":97}],95:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

function createBreadcrumb(
  breadcrumb,
) {
  return {
    timestamp: new Date().getTime() / 1000,
    type: 'default',
    ...breadcrumb,
  };
}

exports.createBreadcrumb = createBreadcrumb;


},{}],96:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

function createPayload({
  events,
  headers,
}

) {
  let payloadWithSequence;

  // XXX: newline is needed to separate sequence id from events
  const replayHeaders = `${JSON.stringify(headers)}
`;

  if (typeof events === 'string') {
    payloadWithSequence = `${replayHeaders}${events}`;
  } else {
    const enc = new TextEncoder();
    // XXX: newline is needed to separate sequence id from events
    const sequence = enc.encode(replayHeaders);
    // Merge the two Uint8Arrays
    payloadWithSequence = new Uint8Array(sequence.length + events.length);
    payloadWithSequence.set(sequence);
    payloadWithSequence.set(events, sequence.length);
  }

  return payloadWithSequence;
}

exports.createPayload = createPayload;


},{}],97:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

require('../node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js');
const addEvent = require('./addEvent.js');
const types = require('../node_modules/rrweb/es/rrweb/packages/rrweb/src/types.js');

/**
 * Create a "span" for each performance entry. The parent transaction is `this.replayEvent`.
 */
function createPerformanceSpans(replay, entries) {
  entries.map(({ type, start, end, name, data }) =>
    addEvent.addEvent(replay, {
      type: types.EventType.Custom,
      timestamp: start,
      data: {
        tag: 'performanceSpan',
        payload: {
          op: type,
          description: name,
          startTimestamp: start,
          endTimestamp: end,
          data,
        },
      },
    }),
  );
}

exports.createPerformanceSpans = createPerformanceSpans;


},{"../node_modules/rrweb/es/rrweb/packages/rrweb/src/entries/all.js":56,"../node_modules/rrweb/es/rrweb/packages/rrweb/src/types.js":84,"./addEvent.js":93}],98:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

function createReplayEnvelope(
  replayEvent,
  payloadWithSequence,
  dsn,
  tunnel,
) {
  return utils.createEnvelope(
    utils.createEventEnvelopeHeaders(replayEvent, utils.getSdkMetadataForEnvelopeHeader(replayEvent), tunnel, dsn),
    [
      // @ts-ignore New types
      [{ type: 'replay_event' }, replayEvent],
      [
        {
          // @ts-ignore setting envelope
          type: 'replay_recording',
          length: payloadWithSequence.length,
        },
        // @ts-ignore: Type 'string' is not assignable to type 'ClientReport'.ts(2322)
        payloadWithSequence,
      ],
    ],
  );
}

exports.createReplayEnvelope = createReplayEnvelope;


},{"@sentry/utils":130}],99:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const NAVIGATION_ENTRY_KEYS = [
  'name',
  'type',
  'startTime',
  'transferSize',
  'duration',
];

function isNavigationEntryEqual(a) {
  return function (b) {
    return NAVIGATION_ENTRY_KEYS.every(key => a[key] === b[key]);
  };
}

/**
 * There are some difficulties diagnosing why there are duplicate navigation
 * entries. We've witnessed several intermittent results:
 * - duplicate entries have duration = 0
 * - duplicate entries are the same object reference
 * - none of the above
 *
 * Compare the values of several keys to determine if the entries are duplicates or not.
 */
// TODO (high-prio): Figure out wth is returned here
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type
function dedupePerformanceEntries(
  currentList,
  newList,
) {
  // Partition `currentList` into 3 different lists based on entryType
  const [existingNavigationEntries, existingLcpEntries, existingEntries] = currentList.reduce(
    (acc, entry) => {
      if (entry.entryType === 'navigation') {
        acc[0].push(entry );
      } else if (entry.entryType === 'largest-contentful-paint') {
        acc[1].push(entry );
      } else {
        acc[2].push(entry);
      }
      return acc;
    },
    [[], [], []],
  );

  const newEntries = [];
  const newNavigationEntries = [];
  let newLcpEntry = existingLcpEntries.length
    ? existingLcpEntries[existingLcpEntries.length - 1] // Take the last element as list is sorted
    : undefined;

  newList.forEach(entry => {
    if (entry.entryType === 'largest-contentful-paint') {
      // We want the latest LCP event only
      if (!newLcpEntry || newLcpEntry.startTime < entry.startTime) {
        newLcpEntry = entry;
      }
      return;
    }

    if (entry.entryType === 'navigation') {
      const navigationEntry = entry ;

      // Check if the navigation entry is contained in currentList or newList
      if (
        // Ignore any navigation entries with duration 0, as they are likely duplicates
        entry.duration > 0 &&
        // Ensure new entry does not already exist in existing entries
        !existingNavigationEntries.find(isNavigationEntryEqual(navigationEntry)) &&
        // Ensure new entry does not already exist in new list of navigation entries
        !newNavigationEntries.find(isNavigationEntryEqual(navigationEntry))
      ) {
        newNavigationEntries.push(navigationEntry);
      }

      // Otherwise this navigation entry is considered a duplicate and is thrown away
      return;
    }

    newEntries.push(entry);
  });

  // Re-combine and sort by startTime
  return [
    ...(newLcpEntry ? [newLcpEntry] : []),
    ...existingNavigationEntries,
    ...existingEntries,
    ...newEntries,
    ...newNavigationEntries,
  ].sort((a, b) => a.startTime - b.startTime);
}

exports.dedupePerformanceEntries = dedupePerformanceEntries;


},{}],100:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

async function getReplayEvent({
  client,
  scope,
  replayId: event_id,
  event,
}

) {
  // XXX: This event does not trigger `beforeSend` in SDK
  // @ts-ignore private api
  const preparedEvent = await client._prepareEvent(event, { event_id }, scope);

  // extract the SDK name because `client._prepareEvent` doesn't add it to the event
  const metadata = client.getOptions() && client.getOptions()._metadata;
  const { name } = (metadata && metadata.sdk) || {};

  preparedEvent.sdk = {
    ...preparedEvent.sdk,
    version: "7.28.0",
    name,
  };

  return preparedEvent;
}

exports.getReplayEvent = getReplayEvent;


},{}],101:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

function isBrowser() {
  // eslint-disable-next-line no-restricted-globals
  return typeof window !== 'undefined' && !utils.isNodeEnv();
}

exports.isBrowser = isBrowser;


},{"@sentry/utils":130}],102:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Given an initial timestamp and an expiry duration, checks to see if current
 * time should be considered as expired.
 */
function isExpired(
  initialTime,
  expiry,
  targetTime = +new Date(),
) {
  // Always expired if < 0
  if (initialTime === null || expiry === undefined || expiry < 0) {
    return true;
  }

  // Never expires if == 0
  if (expiry === 0) {
    return false;
  }

  return initialTime + expiry <= targetTime;
}

exports.isExpired = isExpired;


},{}],103:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

function isRrwebError(event) {
  if (event.type || !_optionalChain([event, 'access', _ => _.exception, 'optionalAccess', _2 => _2.values, 'optionalAccess', _3 => _3.length])) {
    return false;
  }

  // Check if any exception originates from rrweb
  return event.exception.values.some(exception => {
    if (!_optionalChain([exception, 'access', _4 => _4.stacktrace, 'optionalAccess', _5 => _5.frames, 'optionalAccess', _6 => _6.length])) {
      return false;
    }

    return exception.stacktrace.frames.some(frame => _optionalChain([frame, 'access', _7 => _7.filename, 'optionalAccess', _8 => _8.includes, 'call', _9 => _9('/rrweb/src/')]));
  });
}

exports.isRrwebError = isRrwebError;


},{"@sentry/utils/cjs/buildPolyfills":124}],104:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Given a sample rate, returns true if replay should be sampled.
 *
 * 1.0 = 100% sampling
 * 0.0 = 0% sampling
 */
function isSampled(sampleRate) {
  if (sampleRate === undefined) {
    return false;
  }

  // Math.random() returns a number in range of 0 to 1 (inclusive of 0, but not 1)
  return Math.random() < sampleRate;
}

exports.isSampled = isSampled;


},{}],105:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const constants = require('../constants.js');
const isExpired = require('./isExpired.js');

/**
 * Checks to see if session is expired
 */
function isSessionExpired(session, idleTimeout, targetTime = +new Date()) {
  return (
    // First, check that maximum session length has not been exceeded
    isExpired.isExpired(session.started, constants.MAX_SESSION_LIFE, targetTime) ||
    // check that the idle timeout has not been exceeded (i.e. user has
    // performed an action within the last `idleTimeout` ms)
    isExpired.isExpired(_optionalChain([session, 'optionalAccess', _ => _.lastActivity]), idleTimeout, targetTime)
  );
}

exports.isSessionExpired = isSessionExpired;


},{"../constants.js":36,"./isExpired.js":102,"@sentry/utils/cjs/buildPolyfills":124}],106:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');

let _originalRecordDroppedEvent;

function overwriteRecordDroppedEvent(errorIds) {
  const client = core.getCurrentHub().getClient();

  if (!client) {
    return;
  }

  const _originalCallback = client.recordDroppedEvent.bind(client);

  const recordDroppedEvent = (
    reason,
    category,
    event,
  ) => {
    if (event && event.event_id) {
      errorIds.delete(event.event_id);
    }

    return _originalCallback(reason, category, event);
  };

  client.recordDroppedEvent = recordDroppedEvent;
  _originalRecordDroppedEvent = _originalCallback;
}

function restoreRecordDroppedEvent() {
  const client = core.getCurrentHub().getClient();

  if (!client || !_originalRecordDroppedEvent) {
    return;
  }

  client.recordDroppedEvent = _originalRecordDroppedEvent;
}

exports.overwriteRecordDroppedEvent = overwriteRecordDroppedEvent;
exports.restoreRecordDroppedEvent = restoreRecordDroppedEvent;


},{"@sentry/core":24}],107:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils/cjs/buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');

/**
 * Check whether a given request URL should be filtered out.
 */
function shouldFilterRequest(replay, url) {
  // If we enabled the `traceInternals` experiment, we want to trace everything
  if ((typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && _optionalChain([replay, 'access', _ => _.getOptions, 'call', _2 => _2(), 'access', _3 => _3._experiments, 'optionalAccess', _4 => _4.traceInternals])) {
    return false;
  }

  return !_isSentryRequest(url);
}

/**
 * Checks wether a given URL belongs to the configured Sentry DSN.
 */
function _isSentryRequest(url) {
  const dsn = _optionalChain([core.getCurrentHub, 'call', _5 => _5(), 'access', _6 => _6.getClient, 'call', _7 => _7(), 'optionalAccess', _8 => _8.getDsn, 'call', _9 => _9()]);
  return dsn ? url.includes(dsn.host) : false;
}

exports.shouldFilterRequest = shouldFilterRequest;


},{"@sentry/core":24,"@sentry/utils/cjs/buildPolyfills":124}],108:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const workerString = `/*! pako 2.1.0 https://github.com/nodeca/pako @license (MIT AND Zlib) */
function t(t){let e=t.length;for(;--e>=0;)t[e]=0}const e=new Uint8Array([0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0]),a=new Uint8Array([0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13]),i=new Uint8Array([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,3,7]),n=new Uint8Array([16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15]),s=new Array(576);t(s);const r=new Array(60);t(r);const o=new Array(512);t(o);const l=new Array(256);t(l);const h=new Array(29);t(h);const d=new Array(30);function _(t,e,a,i,n){this.static_tree=t,this.extra_bits=e,this.extra_base=a,this.elems=i,this.max_length=n,this.has_stree=t&&t.length}let f,c,u;function w(t,e){this.dyn_tree=t,this.max_code=0,this.stat_desc=e}t(d);const m=t=>t<256?o[t]:o[256+(t>>>7)],b=(t,e)=>{t.pending_buf[t.pending++]=255&e,t.pending_buf[t.pending++]=e>>>8&255},g=(t,e,a)=>{t.bi_valid>16-a?(t.bi_buf|=e<<t.bi_valid&65535,b(t,t.bi_buf),t.bi_buf=e>>16-t.bi_valid,t.bi_valid+=a-16):(t.bi_buf|=e<<t.bi_valid&65535,t.bi_valid+=a)},p=(t,e,a)=>{g(t,a[2*e],a[2*e+1])},k=(t,e)=>{let a=0;do{a|=1&t,t>>>=1,a<<=1}while(--e>0);return a>>>1},v=(t,e,a)=>{const i=new Array(16);let n,s,r=0;for(n=1;n<=15;n++)r=r+a[n-1]<<1,i[n]=r;for(s=0;s<=e;s++){let e=t[2*s+1];0!==e&&(t[2*s]=k(i[e]++,e))}},y=t=>{let e;for(e=0;e<286;e++)t.dyn_ltree[2*e]=0;for(e=0;e<30;e++)t.dyn_dtree[2*e]=0;for(e=0;e<19;e++)t.bl_tree[2*e]=0;t.dyn_ltree[512]=1,t.opt_len=t.static_len=0,t.sym_next=t.matches=0},x=t=>{t.bi_valid>8?b(t,t.bi_buf):t.bi_valid>0&&(t.pending_buf[t.pending++]=t.bi_buf),t.bi_buf=0,t.bi_valid=0},z=(t,e,a,i)=>{const n=2*e,s=2*a;return t[n]<t[s]||t[n]===t[s]&&i[e]<=i[a]},A=(t,e,a)=>{const i=t.heap[a];let n=a<<1;for(;n<=t.heap_len&&(n<t.heap_len&&z(e,t.heap[n+1],t.heap[n],t.depth)&&n++,!z(e,i,t.heap[n],t.depth));)t.heap[a]=t.heap[n],a=n,n<<=1;t.heap[a]=i},E=(t,i,n)=>{let s,r,o,_,f=0;if(0!==t.sym_next)do{s=255&t.pending_buf[t.sym_buf+f++],s+=(255&t.pending_buf[t.sym_buf+f++])<<8,r=t.pending_buf[t.sym_buf+f++],0===s?p(t,r,i):(o=l[r],p(t,o+256+1,i),_=e[o],0!==_&&(r-=h[o],g(t,r,_)),s--,o=m(s),p(t,o,n),_=a[o],0!==_&&(s-=d[o],g(t,s,_)))}while(f<t.sym_next);p(t,256,i)},R=(t,e)=>{const a=e.dyn_tree,i=e.stat_desc.static_tree,n=e.stat_desc.has_stree,s=e.stat_desc.elems;let r,o,l,h=-1;for(t.heap_len=0,t.heap_max=573,r=0;r<s;r++)0!==a[2*r]?(t.heap[++t.heap_len]=h=r,t.depth[r]=0):a[2*r+1]=0;for(;t.heap_len<2;)l=t.heap[++t.heap_len]=h<2?++h:0,a[2*l]=1,t.depth[l]=0,t.opt_len--,n&&(t.static_len-=i[2*l+1]);for(e.max_code=h,r=t.heap_len>>1;r>=1;r--)A(t,a,r);l=s;do{r=t.heap[1],t.heap[1]=t.heap[t.heap_len--],A(t,a,1),o=t.heap[1],t.heap[--t.heap_max]=r,t.heap[--t.heap_max]=o,a[2*l]=a[2*r]+a[2*o],t.depth[l]=(t.depth[r]>=t.depth[o]?t.depth[r]:t.depth[o])+1,a[2*r+1]=a[2*o+1]=l,t.heap[1]=l++,A(t,a,1)}while(t.heap_len>=2);t.heap[--t.heap_max]=t.heap[1],((t,e)=>{const a=e.dyn_tree,i=e.max_code,n=e.stat_desc.static_tree,s=e.stat_desc.has_stree,r=e.stat_desc.extra_bits,o=e.stat_desc.extra_base,l=e.stat_desc.max_length;let h,d,_,f,c,u,w=0;for(f=0;f<=15;f++)t.bl_count[f]=0;for(a[2*t.heap[t.heap_max]+1]=0,h=t.heap_max+1;h<573;h++)d=t.heap[h],f=a[2*a[2*d+1]+1]+1,f>l&&(f=l,w++),a[2*d+1]=f,d>i||(t.bl_count[f]++,c=0,d>=o&&(c=r[d-o]),u=a[2*d],t.opt_len+=u*(f+c),s&&(t.static_len+=u*(n[2*d+1]+c)));if(0!==w){do{for(f=l-1;0===t.bl_count[f];)f--;t.bl_count[f]--,t.bl_count[f+1]+=2,t.bl_count[l]--,w-=2}while(w>0);for(f=l;0!==f;f--)for(d=t.bl_count[f];0!==d;)_=t.heap[--h],_>i||(a[2*_+1]!==f&&(t.opt_len+=(f-a[2*_+1])*a[2*_],a[2*_+1]=f),d--)}})(t,e),v(a,h,t.bl_count)},Z=(t,e,a)=>{let i,n,s=-1,r=e[1],o=0,l=7,h=4;for(0===r&&(l=138,h=3),e[2*(a+1)+1]=65535,i=0;i<=a;i++)n=r,r=e[2*(i+1)+1],++o<l&&n===r||(o<h?t.bl_tree[2*n]+=o:0!==n?(n!==s&&t.bl_tree[2*n]++,t.bl_tree[32]++):o<=10?t.bl_tree[34]++:t.bl_tree[36]++,o=0,s=n,0===r?(l=138,h=3):n===r?(l=6,h=3):(l=7,h=4))},S=(t,e,a)=>{let i,n,s=-1,r=e[1],o=0,l=7,h=4;for(0===r&&(l=138,h=3),i=0;i<=a;i++)if(n=r,r=e[2*(i+1)+1],!(++o<l&&n===r)){if(o<h)do{p(t,n,t.bl_tree)}while(0!=--o);else 0!==n?(n!==s&&(p(t,n,t.bl_tree),o--),p(t,16,t.bl_tree),g(t,o-3,2)):o<=10?(p(t,17,t.bl_tree),g(t,o-3,3)):(p(t,18,t.bl_tree),g(t,o-11,7));o=0,s=n,0===r?(l=138,h=3):n===r?(l=6,h=3):(l=7,h=4)}};let U=!1;const D=(t,e,a,i)=>{g(t,0+(i?1:0),3),x(t),b(t,a),b(t,~a),a&&t.pending_buf.set(t.window.subarray(e,e+a),t.pending),t.pending+=a};var O=(t,e,a,i)=>{let o,l,h=0;t.level>0?(2===t.strm.data_type&&(t.strm.data_type=(t=>{let e,a=4093624447;for(e=0;e<=31;e++,a>>>=1)if(1&a&&0!==t.dyn_ltree[2*e])return 0;if(0!==t.dyn_ltree[18]||0!==t.dyn_ltree[20]||0!==t.dyn_ltree[26])return 1;for(e=32;e<256;e++)if(0!==t.dyn_ltree[2*e])return 1;return 0})(t)),R(t,t.l_desc),R(t,t.d_desc),h=(t=>{let e;for(Z(t,t.dyn_ltree,t.l_desc.max_code),Z(t,t.dyn_dtree,t.d_desc.max_code),R(t,t.bl_desc),e=18;e>=3&&0===t.bl_tree[2*n[e]+1];e--);return t.opt_len+=3*(e+1)+5+5+4,e})(t),o=t.opt_len+3+7>>>3,l=t.static_len+3+7>>>3,l<=o&&(o=l)):o=l=a+5,a+4<=o&&-1!==e?D(t,e,a,i):4===t.strategy||l===o?(g(t,2+(i?1:0),3),E(t,s,r)):(g(t,4+(i?1:0),3),((t,e,a,i)=>{let s;for(g(t,e-257,5),g(t,a-1,5),g(t,i-4,4),s=0;s<i;s++)g(t,t.bl_tree[2*n[s]+1],3);S(t,t.dyn_ltree,e-1),S(t,t.dyn_dtree,a-1)})(t,t.l_desc.max_code+1,t.d_desc.max_code+1,h+1),E(t,t.dyn_ltree,t.dyn_dtree)),y(t),i&&x(t)},T={_tr_init:t=>{U||((()=>{let t,n,w,m,b;const g=new Array(16);for(w=0,m=0;m<28;m++)for(h[m]=w,t=0;t<1<<e[m];t++)l[w++]=m;for(l[w-1]=m,b=0,m=0;m<16;m++)for(d[m]=b,t=0;t<1<<a[m];t++)o[b++]=m;for(b>>=7;m<30;m++)for(d[m]=b<<7,t=0;t<1<<a[m]-7;t++)o[256+b++]=m;for(n=0;n<=15;n++)g[n]=0;for(t=0;t<=143;)s[2*t+1]=8,t++,g[8]++;for(;t<=255;)s[2*t+1]=9,t++,g[9]++;for(;t<=279;)s[2*t+1]=7,t++,g[7]++;for(;t<=287;)s[2*t+1]=8,t++,g[8]++;for(v(s,287,g),t=0;t<30;t++)r[2*t+1]=5,r[2*t]=k(t,5);f=new _(s,e,257,286,15),c=new _(r,a,0,30,15),u=new _(new Array(0),i,0,19,7)})(),U=!0),t.l_desc=new w(t.dyn_ltree,f),t.d_desc=new w(t.dyn_dtree,c),t.bl_desc=new w(t.bl_tree,u),t.bi_buf=0,t.bi_valid=0,y(t)},_tr_stored_block:D,_tr_flush_block:O,_tr_tally:(t,e,a)=>(t.pending_buf[t.sym_buf+t.sym_next++]=e,t.pending_buf[t.sym_buf+t.sym_next++]=e>>8,t.pending_buf[t.sym_buf+t.sym_next++]=a,0===e?t.dyn_ltree[2*a]++:(t.matches++,e--,t.dyn_ltree[2*(l[a]+256+1)]++,t.dyn_dtree[2*m(e)]++),t.sym_next===t.sym_end),_tr_align:t=>{g(t,2,3),p(t,256,s),(t=>{16===t.bi_valid?(b(t,t.bi_buf),t.bi_buf=0,t.bi_valid=0):t.bi_valid>=8&&(t.pending_buf[t.pending++]=255&t.bi_buf,t.bi_buf>>=8,t.bi_valid-=8)})(t)}};var N=(t,e,a,i)=>{let n=65535&t|0,s=t>>>16&65535|0,r=0;for(;0!==a;){r=a>2e3?2e3:a,a-=r;do{n=n+e[i++]|0,s=s+n|0}while(--r);n%=65521,s%=65521}return n|s<<16|0};const F=new Uint32Array((()=>{let t,e=[];for(var a=0;a<256;a++){t=a;for(var i=0;i<8;i++)t=1&t?3988292384^t>>>1:t>>>1;e[a]=t}return e})());var L=(t,e,a,i)=>{const n=F,s=i+a;t^=-1;for(let a=i;a<s;a++)t=t>>>8^n[255&(t^e[a])];return-1^t},I={2:"need dictionary",1:"stream end",0:"","-1":"file error","-2":"stream error","-3":"data error","-4":"insufficient memory","-5":"buffer error","-6":"incompatible version"},B={Z_NO_FLUSH:0,Z_PARTIAL_FLUSH:1,Z_SYNC_FLUSH:2,Z_FULL_FLUSH:3,Z_FINISH:4,Z_BLOCK:5,Z_TREES:6,Z_OK:0,Z_STREAM_END:1,Z_NEED_DICT:2,Z_ERRNO:-1,Z_STREAM_ERROR:-2,Z_DATA_ERROR:-3,Z_MEM_ERROR:-4,Z_BUF_ERROR:-5,Z_NO_COMPRESSION:0,Z_BEST_SPEED:1,Z_BEST_COMPRESSION:9,Z_DEFAULT_COMPRESSION:-1,Z_FILTERED:1,Z_HUFFMAN_ONLY:2,Z_RLE:3,Z_FIXED:4,Z_DEFAULT_STRATEGY:0,Z_BINARY:0,Z_TEXT:1,Z_UNKNOWN:2,Z_DEFLATED:8};const{_tr_init:C,_tr_stored_block:H,_tr_flush_block:M,_tr_tally:j,_tr_align:K}=T,{Z_NO_FLUSH:P,Z_PARTIAL_FLUSH:Y,Z_FULL_FLUSH:G,Z_FINISH:X,Z_BLOCK:J,Z_OK:W,Z_STREAM_END:q,Z_STREAM_ERROR:Q,Z_DATA_ERROR:V,Z_BUF_ERROR:$,Z_DEFAULT_COMPRESSION:tt,Z_FILTERED:et,Z_HUFFMAN_ONLY:at,Z_RLE:it,Z_FIXED:nt,Z_DEFAULT_STRATEGY:st,Z_UNKNOWN:rt,Z_DEFLATED:ot}=B,lt=(t,e)=>(t.msg=I[e],e),ht=t=>2*t-(t>4?9:0),dt=t=>{let e=t.length;for(;--e>=0;)t[e]=0},_t=t=>{let e,a,i,n=t.w_size;e=t.hash_size,i=e;do{a=t.head[--i],t.head[i]=a>=n?a-n:0}while(--e);e=n,i=e;do{a=t.prev[--i],t.prev[i]=a>=n?a-n:0}while(--e)};let ft=(t,e,a)=>(e<<t.hash_shift^a)&t.hash_mask;const ct=t=>{const e=t.state;let a=e.pending;a>t.avail_out&&(a=t.avail_out),0!==a&&(t.output.set(e.pending_buf.subarray(e.pending_out,e.pending_out+a),t.next_out),t.next_out+=a,e.pending_out+=a,t.total_out+=a,t.avail_out-=a,e.pending-=a,0===e.pending&&(e.pending_out=0))},ut=(t,e)=>{M(t,t.block_start>=0?t.block_start:-1,t.strstart-t.block_start,e),t.block_start=t.strstart,ct(t.strm)},wt=(t,e)=>{t.pending_buf[t.pending++]=e},mt=(t,e)=>{t.pending_buf[t.pending++]=e>>>8&255,t.pending_buf[t.pending++]=255&e},bt=(t,e,a,i)=>{let n=t.avail_in;return n>i&&(n=i),0===n?0:(t.avail_in-=n,e.set(t.input.subarray(t.next_in,t.next_in+n),a),1===t.state.wrap?t.adler=N(t.adler,e,n,a):2===t.state.wrap&&(t.adler=L(t.adler,e,n,a)),t.next_in+=n,t.total_in+=n,n)},gt=(t,e)=>{let a,i,n=t.max_chain_length,s=t.strstart,r=t.prev_length,o=t.nice_match;const l=t.strstart>t.w_size-262?t.strstart-(t.w_size-262):0,h=t.window,d=t.w_mask,_=t.prev,f=t.strstart+258;let c=h[s+r-1],u=h[s+r];t.prev_length>=t.good_match&&(n>>=2),o>t.lookahead&&(o=t.lookahead);do{if(a=e,h[a+r]===u&&h[a+r-1]===c&&h[a]===h[s]&&h[++a]===h[s+1]){s+=2,a++;do{}while(h[++s]===h[++a]&&h[++s]===h[++a]&&h[++s]===h[++a]&&h[++s]===h[++a]&&h[++s]===h[++a]&&h[++s]===h[++a]&&h[++s]===h[++a]&&h[++s]===h[++a]&&s<f);if(i=258-(f-s),s=f-258,i>r){if(t.match_start=e,r=i,i>=o)break;c=h[s+r-1],u=h[s+r]}}}while((e=_[e&d])>l&&0!=--n);return r<=t.lookahead?r:t.lookahead},pt=t=>{const e=t.w_size;let a,i,n;do{if(i=t.window_size-t.lookahead-t.strstart,t.strstart>=e+(e-262)&&(t.window.set(t.window.subarray(e,e+e-i),0),t.match_start-=e,t.strstart-=e,t.block_start-=e,t.insert>t.strstart&&(t.insert=t.strstart),_t(t),i+=e),0===t.strm.avail_in)break;if(a=bt(t.strm,t.window,t.strstart+t.lookahead,i),t.lookahead+=a,t.lookahead+t.insert>=3)for(n=t.strstart-t.insert,t.ins_h=t.window[n],t.ins_h=ft(t,t.ins_h,t.window[n+1]);t.insert&&(t.ins_h=ft(t,t.ins_h,t.window[n+3-1]),t.prev[n&t.w_mask]=t.head[t.ins_h],t.head[t.ins_h]=n,n++,t.insert--,!(t.lookahead+t.insert<3)););}while(t.lookahead<262&&0!==t.strm.avail_in)},kt=(t,e)=>{let a,i,n,s=t.pending_buf_size-5>t.w_size?t.w_size:t.pending_buf_size-5,r=0,o=t.strm.avail_in;do{if(a=65535,n=t.bi_valid+42>>3,t.strm.avail_out<n)break;if(n=t.strm.avail_out-n,i=t.strstart-t.block_start,a>i+t.strm.avail_in&&(a=i+t.strm.avail_in),a>n&&(a=n),a<s&&(0===a&&e!==X||e===P||a!==i+t.strm.avail_in))break;r=e===X&&a===i+t.strm.avail_in?1:0,H(t,0,0,r),t.pending_buf[t.pending-4]=a,t.pending_buf[t.pending-3]=a>>8,t.pending_buf[t.pending-2]=~a,t.pending_buf[t.pending-1]=~a>>8,ct(t.strm),i&&(i>a&&(i=a),t.strm.output.set(t.window.subarray(t.block_start,t.block_start+i),t.strm.next_out),t.strm.next_out+=i,t.strm.avail_out-=i,t.strm.total_out+=i,t.block_start+=i,a-=i),a&&(bt(t.strm,t.strm.output,t.strm.next_out,a),t.strm.next_out+=a,t.strm.avail_out-=a,t.strm.total_out+=a)}while(0===r);return o-=t.strm.avail_in,o&&(o>=t.w_size?(t.matches=2,t.window.set(t.strm.input.subarray(t.strm.next_in-t.w_size,t.strm.next_in),0),t.strstart=t.w_size,t.insert=t.strstart):(t.window_size-t.strstart<=o&&(t.strstart-=t.w_size,t.window.set(t.window.subarray(t.w_size,t.w_size+t.strstart),0),t.matches<2&&t.matches++,t.insert>t.strstart&&(t.insert=t.strstart)),t.window.set(t.strm.input.subarray(t.strm.next_in-o,t.strm.next_in),t.strstart),t.strstart+=o,t.insert+=o>t.w_size-t.insert?t.w_size-t.insert:o),t.block_start=t.strstart),t.high_water<t.strstart&&(t.high_water=t.strstart),r?4:e!==P&&e!==X&&0===t.strm.avail_in&&t.strstart===t.block_start?2:(n=t.window_size-t.strstart,t.strm.avail_in>n&&t.block_start>=t.w_size&&(t.block_start-=t.w_size,t.strstart-=t.w_size,t.window.set(t.window.subarray(t.w_size,t.w_size+t.strstart),0),t.matches<2&&t.matches++,n+=t.w_size,t.insert>t.strstart&&(t.insert=t.strstart)),n>t.strm.avail_in&&(n=t.strm.avail_in),n&&(bt(t.strm,t.window,t.strstart,n),t.strstart+=n,t.insert+=n>t.w_size-t.insert?t.w_size-t.insert:n),t.high_water<t.strstart&&(t.high_water=t.strstart),n=t.bi_valid+42>>3,n=t.pending_buf_size-n>65535?65535:t.pending_buf_size-n,s=n>t.w_size?t.w_size:n,i=t.strstart-t.block_start,(i>=s||(i||e===X)&&e!==P&&0===t.strm.avail_in&&i<=n)&&(a=i>n?n:i,r=e===X&&0===t.strm.avail_in&&a===i?1:0,H(t,t.block_start,a,r),t.block_start+=a,ct(t.strm)),r?3:1)},vt=(t,e)=>{let a,i;for(;;){if(t.lookahead<262){if(pt(t),t.lookahead<262&&e===P)return 1;if(0===t.lookahead)break}if(a=0,t.lookahead>=3&&(t.ins_h=ft(t,t.ins_h,t.window[t.strstart+3-1]),a=t.prev[t.strstart&t.w_mask]=t.head[t.ins_h],t.head[t.ins_h]=t.strstart),0!==a&&t.strstart-a<=t.w_size-262&&(t.match_length=gt(t,a)),t.match_length>=3)if(i=j(t,t.strstart-t.match_start,t.match_length-3),t.lookahead-=t.match_length,t.match_length<=t.max_lazy_match&&t.lookahead>=3){t.match_length--;do{t.strstart++,t.ins_h=ft(t,t.ins_h,t.window[t.strstart+3-1]),a=t.prev[t.strstart&t.w_mask]=t.head[t.ins_h],t.head[t.ins_h]=t.strstart}while(0!=--t.match_length);t.strstart++}else t.strstart+=t.match_length,t.match_length=0,t.ins_h=t.window[t.strstart],t.ins_h=ft(t,t.ins_h,t.window[t.strstart+1]);else i=j(t,0,t.window[t.strstart]),t.lookahead--,t.strstart++;if(i&&(ut(t,!1),0===t.strm.avail_out))return 1}return t.insert=t.strstart<2?t.strstart:2,e===X?(ut(t,!0),0===t.strm.avail_out?3:4):t.sym_next&&(ut(t,!1),0===t.strm.avail_out)?1:2},yt=(t,e)=>{let a,i,n;for(;;){if(t.lookahead<262){if(pt(t),t.lookahead<262&&e===P)return 1;if(0===t.lookahead)break}if(a=0,t.lookahead>=3&&(t.ins_h=ft(t,t.ins_h,t.window[t.strstart+3-1]),a=t.prev[t.strstart&t.w_mask]=t.head[t.ins_h],t.head[t.ins_h]=t.strstart),t.prev_length=t.match_length,t.prev_match=t.match_start,t.match_length=2,0!==a&&t.prev_length<t.max_lazy_match&&t.strstart-a<=t.w_size-262&&(t.match_length=gt(t,a),t.match_length<=5&&(t.strategy===et||3===t.match_length&&t.strstart-t.match_start>4096)&&(t.match_length=2)),t.prev_length>=3&&t.match_length<=t.prev_length){n=t.strstart+t.lookahead-3,i=j(t,t.strstart-1-t.prev_match,t.prev_length-3),t.lookahead-=t.prev_length-1,t.prev_length-=2;do{++t.strstart<=n&&(t.ins_h=ft(t,t.ins_h,t.window[t.strstart+3-1]),a=t.prev[t.strstart&t.w_mask]=t.head[t.ins_h],t.head[t.ins_h]=t.strstart)}while(0!=--t.prev_length);if(t.match_available=0,t.match_length=2,t.strstart++,i&&(ut(t,!1),0===t.strm.avail_out))return 1}else if(t.match_available){if(i=j(t,0,t.window[t.strstart-1]),i&&ut(t,!1),t.strstart++,t.lookahead--,0===t.strm.avail_out)return 1}else t.match_available=1,t.strstart++,t.lookahead--}return t.match_available&&(i=j(t,0,t.window[t.strstart-1]),t.match_available=0),t.insert=t.strstart<2?t.strstart:2,e===X?(ut(t,!0),0===t.strm.avail_out?3:4):t.sym_next&&(ut(t,!1),0===t.strm.avail_out)?1:2};function xt(t,e,a,i,n){this.good_length=t,this.max_lazy=e,this.nice_length=a,this.max_chain=i,this.func=n}const zt=[new xt(0,0,0,0,kt),new xt(4,4,8,4,vt),new xt(4,5,16,8,vt),new xt(4,6,32,32,vt),new xt(4,4,16,16,yt),new xt(8,16,32,32,yt),new xt(8,16,128,128,yt),new xt(8,32,128,256,yt),new xt(32,128,258,1024,yt),new xt(32,258,258,4096,yt)];function At(){this.strm=null,this.status=0,this.pending_buf=null,this.pending_buf_size=0,this.pending_out=0,this.pending=0,this.wrap=0,this.gzhead=null,this.gzindex=0,this.method=ot,this.last_flush=-1,this.w_size=0,this.w_bits=0,this.w_mask=0,this.window=null,this.window_size=0,this.prev=null,this.head=null,this.ins_h=0,this.hash_size=0,this.hash_bits=0,this.hash_mask=0,this.hash_shift=0,this.block_start=0,this.match_length=0,this.prev_match=0,this.match_available=0,this.strstart=0,this.match_start=0,this.lookahead=0,this.prev_length=0,this.max_chain_length=0,this.max_lazy_match=0,this.level=0,this.strategy=0,this.good_match=0,this.nice_match=0,this.dyn_ltree=new Uint16Array(1146),this.dyn_dtree=new Uint16Array(122),this.bl_tree=new Uint16Array(78),dt(this.dyn_ltree),dt(this.dyn_dtree),dt(this.bl_tree),this.l_desc=null,this.d_desc=null,this.bl_desc=null,this.bl_count=new Uint16Array(16),this.heap=new Uint16Array(573),dt(this.heap),this.heap_len=0,this.heap_max=0,this.depth=new Uint16Array(573),dt(this.depth),this.sym_buf=0,this.lit_bufsize=0,this.sym_next=0,this.sym_end=0,this.opt_len=0,this.static_len=0,this.matches=0,this.insert=0,this.bi_buf=0,this.bi_valid=0}const Et=t=>{if(!t)return 1;const e=t.state;return!e||e.strm!==t||42!==e.status&&57!==e.status&&69!==e.status&&73!==e.status&&91!==e.status&&103!==e.status&&113!==e.status&&666!==e.status?1:0},Rt=t=>{if(Et(t))return lt(t,Q);t.total_in=t.total_out=0,t.data_type=rt;const e=t.state;return e.pending=0,e.pending_out=0,e.wrap<0&&(e.wrap=-e.wrap),e.status=2===e.wrap?57:e.wrap?42:113,t.adler=2===e.wrap?0:1,e.last_flush=-2,C(e),W},Zt=t=>{const e=Rt(t);var a;return e===W&&((a=t.state).window_size=2*a.w_size,dt(a.head),a.max_lazy_match=zt[a.level].max_lazy,a.good_match=zt[a.level].good_length,a.nice_match=zt[a.level].nice_length,a.max_chain_length=zt[a.level].max_chain,a.strstart=0,a.block_start=0,a.lookahead=0,a.insert=0,a.match_length=a.prev_length=2,a.match_available=0,a.ins_h=0),e},St=(t,e,a,i,n,s)=>{if(!t)return Q;let r=1;if(e===tt&&(e=6),i<0?(r=0,i=-i):i>15&&(r=2,i-=16),n<1||n>9||a!==ot||i<8||i>15||e<0||e>9||s<0||s>nt||8===i&&1!==r)return lt(t,Q);8===i&&(i=9);const o=new At;return t.state=o,o.strm=t,o.status=42,o.wrap=r,o.gzhead=null,o.w_bits=i,o.w_size=1<<o.w_bits,o.w_mask=o.w_size-1,o.hash_bits=n+7,o.hash_size=1<<o.hash_bits,o.hash_mask=o.hash_size-1,o.hash_shift=~~((o.hash_bits+3-1)/3),o.window=new Uint8Array(2*o.w_size),o.head=new Uint16Array(o.hash_size),o.prev=new Uint16Array(o.w_size),o.lit_bufsize=1<<n+6,o.pending_buf_size=4*o.lit_bufsize,o.pending_buf=new Uint8Array(o.pending_buf_size),o.sym_buf=o.lit_bufsize,o.sym_end=3*(o.lit_bufsize-1),o.level=e,o.strategy=s,o.method=a,Zt(t)};var Ut={deflateInit:(t,e)=>St(t,e,ot,15,8,st),deflateInit2:St,deflateReset:Zt,deflateResetKeep:Rt,deflateSetHeader:(t,e)=>Et(t)||2!==t.state.wrap?Q:(t.state.gzhead=e,W),deflate:(t,e)=>{if(Et(t)||e>J||e<0)return t?lt(t,Q):Q;const a=t.state;if(!t.output||0!==t.avail_in&&!t.input||666===a.status&&e!==X)return lt(t,0===t.avail_out?$:Q);const i=a.last_flush;if(a.last_flush=e,0!==a.pending){if(ct(t),0===t.avail_out)return a.last_flush=-1,W}else if(0===t.avail_in&&ht(e)<=ht(i)&&e!==X)return lt(t,$);if(666===a.status&&0!==t.avail_in)return lt(t,$);if(42===a.status&&0===a.wrap&&(a.status=113),42===a.status){let e=ot+(a.w_bits-8<<4)<<8,i=-1;if(i=a.strategy>=at||a.level<2?0:a.level<6?1:6===a.level?2:3,e|=i<<6,0!==a.strstart&&(e|=32),e+=31-e%31,mt(a,e),0!==a.strstart&&(mt(a,t.adler>>>16),mt(a,65535&t.adler)),t.adler=1,a.status=113,ct(t),0!==a.pending)return a.last_flush=-1,W}if(57===a.status)if(t.adler=0,wt(a,31),wt(a,139),wt(a,8),a.gzhead)wt(a,(a.gzhead.text?1:0)+(a.gzhead.hcrc?2:0)+(a.gzhead.extra?4:0)+(a.gzhead.name?8:0)+(a.gzhead.comment?16:0)),wt(a,255&a.gzhead.time),wt(a,a.gzhead.time>>8&255),wt(a,a.gzhead.time>>16&255),wt(a,a.gzhead.time>>24&255),wt(a,9===a.level?2:a.strategy>=at||a.level<2?4:0),wt(a,255&a.gzhead.os),a.gzhead.extra&&a.gzhead.extra.length&&(wt(a,255&a.gzhead.extra.length),wt(a,a.gzhead.extra.length>>8&255)),a.gzhead.hcrc&&(t.adler=L(t.adler,a.pending_buf,a.pending,0)),a.gzindex=0,a.status=69;else if(wt(a,0),wt(a,0),wt(a,0),wt(a,0),wt(a,0),wt(a,9===a.level?2:a.strategy>=at||a.level<2?4:0),wt(a,3),a.status=113,ct(t),0!==a.pending)return a.last_flush=-1,W;if(69===a.status){if(a.gzhead.extra){let e=a.pending,i=(65535&a.gzhead.extra.length)-a.gzindex;for(;a.pending+i>a.pending_buf_size;){let n=a.pending_buf_size-a.pending;if(a.pending_buf.set(a.gzhead.extra.subarray(a.gzindex,a.gzindex+n),a.pending),a.pending=a.pending_buf_size,a.gzhead.hcrc&&a.pending>e&&(t.adler=L(t.adler,a.pending_buf,a.pending-e,e)),a.gzindex+=n,ct(t),0!==a.pending)return a.last_flush=-1,W;e=0,i-=n}let n=new Uint8Array(a.gzhead.extra);a.pending_buf.set(n.subarray(a.gzindex,a.gzindex+i),a.pending),a.pending+=i,a.gzhead.hcrc&&a.pending>e&&(t.adler=L(t.adler,a.pending_buf,a.pending-e,e)),a.gzindex=0}a.status=73}if(73===a.status){if(a.gzhead.name){let e,i=a.pending;do{if(a.pending===a.pending_buf_size){if(a.gzhead.hcrc&&a.pending>i&&(t.adler=L(t.adler,a.pending_buf,a.pending-i,i)),ct(t),0!==a.pending)return a.last_flush=-1,W;i=0}e=a.gzindex<a.gzhead.name.length?255&a.gzhead.name.charCodeAt(a.gzindex++):0,wt(a,e)}while(0!==e);a.gzhead.hcrc&&a.pending>i&&(t.adler=L(t.adler,a.pending_buf,a.pending-i,i)),a.gzindex=0}a.status=91}if(91===a.status){if(a.gzhead.comment){let e,i=a.pending;do{if(a.pending===a.pending_buf_size){if(a.gzhead.hcrc&&a.pending>i&&(t.adler=L(t.adler,a.pending_buf,a.pending-i,i)),ct(t),0!==a.pending)return a.last_flush=-1,W;i=0}e=a.gzindex<a.gzhead.comment.length?255&a.gzhead.comment.charCodeAt(a.gzindex++):0,wt(a,e)}while(0!==e);a.gzhead.hcrc&&a.pending>i&&(t.adler=L(t.adler,a.pending_buf,a.pending-i,i))}a.status=103}if(103===a.status){if(a.gzhead.hcrc){if(a.pending+2>a.pending_buf_size&&(ct(t),0!==a.pending))return a.last_flush=-1,W;wt(a,255&t.adler),wt(a,t.adler>>8&255),t.adler=0}if(a.status=113,ct(t),0!==a.pending)return a.last_flush=-1,W}if(0!==t.avail_in||0!==a.lookahead||e!==P&&666!==a.status){let i=0===a.level?kt(a,e):a.strategy===at?((t,e)=>{let a;for(;;){if(0===t.lookahead&&(pt(t),0===t.lookahead)){if(e===P)return 1;break}if(t.match_length=0,a=j(t,0,t.window[t.strstart]),t.lookahead--,t.strstart++,a&&(ut(t,!1),0===t.strm.avail_out))return 1}return t.insert=0,e===X?(ut(t,!0),0===t.strm.avail_out?3:4):t.sym_next&&(ut(t,!1),0===t.strm.avail_out)?1:2})(a,e):a.strategy===it?((t,e)=>{let a,i,n,s;const r=t.window;for(;;){if(t.lookahead<=258){if(pt(t),t.lookahead<=258&&e===P)return 1;if(0===t.lookahead)break}if(t.match_length=0,t.lookahead>=3&&t.strstart>0&&(n=t.strstart-1,i=r[n],i===r[++n]&&i===r[++n]&&i===r[++n])){s=t.strstart+258;do{}while(i===r[++n]&&i===r[++n]&&i===r[++n]&&i===r[++n]&&i===r[++n]&&i===r[++n]&&i===r[++n]&&i===r[++n]&&n<s);t.match_length=258-(s-n),t.match_length>t.lookahead&&(t.match_length=t.lookahead)}if(t.match_length>=3?(a=j(t,1,t.match_length-3),t.lookahead-=t.match_length,t.strstart+=t.match_length,t.match_length=0):(a=j(t,0,t.window[t.strstart]),t.lookahead--,t.strstart++),a&&(ut(t,!1),0===t.strm.avail_out))return 1}return t.insert=0,e===X?(ut(t,!0),0===t.strm.avail_out?3:4):t.sym_next&&(ut(t,!1),0===t.strm.avail_out)?1:2})(a,e):zt[a.level].func(a,e);if(3!==i&&4!==i||(a.status=666),1===i||3===i)return 0===t.avail_out&&(a.last_flush=-1),W;if(2===i&&(e===Y?K(a):e!==J&&(H(a,0,0,!1),e===G&&(dt(a.head),0===a.lookahead&&(a.strstart=0,a.block_start=0,a.insert=0))),ct(t),0===t.avail_out))return a.last_flush=-1,W}return e!==X?W:a.wrap<=0?q:(2===a.wrap?(wt(a,255&t.adler),wt(a,t.adler>>8&255),wt(a,t.adler>>16&255),wt(a,t.adler>>24&255),wt(a,255&t.total_in),wt(a,t.total_in>>8&255),wt(a,t.total_in>>16&255),wt(a,t.total_in>>24&255)):(mt(a,t.adler>>>16),mt(a,65535&t.adler)),ct(t),a.wrap>0&&(a.wrap=-a.wrap),0!==a.pending?W:q)},deflateEnd:t=>{if(Et(t))return Q;const e=t.state.status;return t.state=null,113===e?lt(t,V):W},deflateSetDictionary:(t,e)=>{let a=e.length;if(Et(t))return Q;const i=t.state,n=i.wrap;if(2===n||1===n&&42!==i.status||i.lookahead)return Q;if(1===n&&(t.adler=N(t.adler,e,a,0)),i.wrap=0,a>=i.w_size){0===n&&(dt(i.head),i.strstart=0,i.block_start=0,i.insert=0);let t=new Uint8Array(i.w_size);t.set(e.subarray(a-i.w_size,a),0),e=t,a=i.w_size}const s=t.avail_in,r=t.next_in,o=t.input;for(t.avail_in=a,t.next_in=0,t.input=e,pt(i);i.lookahead>=3;){let t=i.strstart,e=i.lookahead-2;do{i.ins_h=ft(i,i.ins_h,i.window[t+3-1]),i.prev[t&i.w_mask]=i.head[i.ins_h],i.head[i.ins_h]=t,t++}while(--e);i.strstart=t,i.lookahead=2,pt(i)}return i.strstart+=i.lookahead,i.block_start=i.strstart,i.insert=i.lookahead,i.lookahead=0,i.match_length=i.prev_length=2,i.match_available=0,t.next_in=r,t.input=o,t.avail_in=s,i.wrap=n,W},deflateInfo:"pako deflate (from Nodeca project)"};const Dt=(t,e)=>Object.prototype.hasOwnProperty.call(t,e);var Ot=function(t){const e=Array.prototype.slice.call(arguments,1);for(;e.length;){const a=e.shift();if(a){if("object"!=typeof a)throw new TypeError(a+"must be non-object");for(const e in a)Dt(a,e)&&(t[e]=a[e])}}return t},Tt=t=>{let e=0;for(let a=0,i=t.length;a<i;a++)e+=t[a].length;const a=new Uint8Array(e);for(let e=0,i=0,n=t.length;e<n;e++){let n=t[e];a.set(n,i),i+=n.length}return a};let Nt=!0;try{String.fromCharCode.apply(null,new Uint8Array(1))}catch(t){Nt=!1}const Ft=new Uint8Array(256);for(let t=0;t<256;t++)Ft[t]=t>=252?6:t>=248?5:t>=240?4:t>=224?3:t>=192?2:1;Ft[254]=Ft[254]=1;var Lt=t=>{if("function"==typeof TextEncoder&&TextEncoder.prototype.encode)return(new TextEncoder).encode(t);let e,a,i,n,s,r=t.length,o=0;for(n=0;n<r;n++)a=t.charCodeAt(n),55296==(64512&a)&&n+1<r&&(i=t.charCodeAt(n+1),56320==(64512&i)&&(a=65536+(a-55296<<10)+(i-56320),n++)),o+=a<128?1:a<2048?2:a<65536?3:4;for(e=new Uint8Array(o),s=0,n=0;s<o;n++)a=t.charCodeAt(n),55296==(64512&a)&&n+1<r&&(i=t.charCodeAt(n+1),56320==(64512&i)&&(a=65536+(a-55296<<10)+(i-56320),n++)),a<128?e[s++]=a:a<2048?(e[s++]=192|a>>>6,e[s++]=128|63&a):a<65536?(e[s++]=224|a>>>12,e[s++]=128|a>>>6&63,e[s++]=128|63&a):(e[s++]=240|a>>>18,e[s++]=128|a>>>12&63,e[s++]=128|a>>>6&63,e[s++]=128|63&a);return e},It=(t,e)=>{const a=e||t.length;if("function"==typeof TextDecoder&&TextDecoder.prototype.decode)return(new TextDecoder).decode(t.subarray(0,e));let i,n;const s=new Array(2*a);for(n=0,i=0;i<a;){let e=t[i++];if(e<128){s[n++]=e;continue}let r=Ft[e];if(r>4)s[n++]=65533,i+=r-1;else{for(e&=2===r?31:3===r?15:7;r>1&&i<a;)e=e<<6|63&t[i++],r--;r>1?s[n++]=65533:e<65536?s[n++]=e:(e-=65536,s[n++]=55296|e>>10&1023,s[n++]=56320|1023&e)}}return((t,e)=>{if(e<65534&&t.subarray&&Nt)return String.fromCharCode.apply(null,t.length===e?t:t.subarray(0,e));let a="";for(let i=0;i<e;i++)a+=String.fromCharCode(t[i]);return a})(s,n)},Bt=(t,e)=>{(e=e||t.length)>t.length&&(e=t.length);let a=e-1;for(;a>=0&&128==(192&t[a]);)a--;return a<0||0===a?e:a+Ft[t[a]]>e?a:e};var Ct=function(){this.input=null,this.next_in=0,this.avail_in=0,this.total_in=0,this.output=null,this.next_out=0,this.avail_out=0,this.total_out=0,this.msg="",this.state=null,this.data_type=2,this.adler=0};const Ht=Object.prototype.toString,{Z_NO_FLUSH:Mt,Z_SYNC_FLUSH:jt,Z_FULL_FLUSH:Kt,Z_FINISH:Pt,Z_OK:Yt,Z_STREAM_END:Gt,Z_DEFAULT_COMPRESSION:Xt,Z_DEFAULT_STRATEGY:Jt,Z_DEFLATED:Wt}=B;function qt(t){this.options=Ot({level:Xt,method:Wt,chunkSize:16384,windowBits:15,memLevel:8,strategy:Jt},t||{});let e=this.options;e.raw&&e.windowBits>0?e.windowBits=-e.windowBits:e.gzip&&e.windowBits>0&&e.windowBits<16&&(e.windowBits+=16),this.err=0,this.msg="",this.ended=!1,this.chunks=[],this.strm=new Ct,this.strm.avail_out=0;let a=Ut.deflateInit2(this.strm,e.level,e.method,e.windowBits,e.memLevel,e.strategy);if(a!==Yt)throw new Error(I[a]);if(e.header&&Ut.deflateSetHeader(this.strm,e.header),e.dictionary){let t;if(t="string"==typeof e.dictionary?Lt(e.dictionary):"[object ArrayBuffer]"===Ht.call(e.dictionary)?new Uint8Array(e.dictionary):e.dictionary,a=Ut.deflateSetDictionary(this.strm,t),a!==Yt)throw new Error(I[a]);this._dict_set=!0}}function Qt(t,e){const a=new qt(e);if(a.push(t,!0),a.err)throw a.msg||I[a.err];return a.result}qt.prototype.push=function(t,e){const a=this.strm,i=this.options.chunkSize;let n,s;if(this.ended)return!1;for(s=e===~~e?e:!0===e?Pt:Mt,"string"==typeof t?a.input=Lt(t):"[object ArrayBuffer]"===Ht.call(t)?a.input=new Uint8Array(t):a.input=t,a.next_in=0,a.avail_in=a.input.length;;)if(0===a.avail_out&&(a.output=new Uint8Array(i),a.next_out=0,a.avail_out=i),(s===jt||s===Kt)&&a.avail_out<=6)this.onData(a.output.subarray(0,a.next_out)),a.avail_out=0;else{if(n=Ut.deflate(a,s),n===Gt)return a.next_out>0&&this.onData(a.output.subarray(0,a.next_out)),n=Ut.deflateEnd(this.strm),this.onEnd(n),this.ended=!0,n===Yt;if(0!==a.avail_out){if(s>0&&a.next_out>0)this.onData(a.output.subarray(0,a.next_out)),a.avail_out=0;else if(0===a.avail_in)break}else this.onData(a.output)}return!0},qt.prototype.onData=function(t){this.chunks.push(t)},qt.prototype.onEnd=function(t){t===Yt&&(this.result=Tt(this.chunks)),this.chunks=[],this.err=t,this.msg=this.strm.msg};var Vt={Deflate:qt,deflate:Qt,deflateRaw:function(t,e){return(e=e||{}).raw=!0,Qt(t,e)},gzip:function(t,e){return(e=e||{}).gzip=!0,Qt(t,e)},constants:B};var $t=function(t,e){let a,i,n,s,r,o,l,h,d,_,f,c,u,w,m,b,g,p,k,v,y,x,z,A;const E=t.state;a=t.next_in,z=t.input,i=a+(t.avail_in-5),n=t.next_out,A=t.output,s=n-(e-t.avail_out),r=n+(t.avail_out-257),o=E.dmax,l=E.wsize,h=E.whave,d=E.wnext,_=E.window,f=E.hold,c=E.bits,u=E.lencode,w=E.distcode,m=(1<<E.lenbits)-1,b=(1<<E.distbits)-1;t:do{c<15&&(f+=z[a++]<<c,c+=8,f+=z[a++]<<c,c+=8),g=u[f&m];e:for(;;){if(p=g>>>24,f>>>=p,c-=p,p=g>>>16&255,0===p)A[n++]=65535&g;else{if(!(16&p)){if(0==(64&p)){g=u[(65535&g)+(f&(1<<p)-1)];continue e}if(32&p){E.mode=16191;break t}t.msg="invalid literal/length code",E.mode=16209;break t}k=65535&g,p&=15,p&&(c<p&&(f+=z[a++]<<c,c+=8),k+=f&(1<<p)-1,f>>>=p,c-=p),c<15&&(f+=z[a++]<<c,c+=8,f+=z[a++]<<c,c+=8),g=w[f&b];a:for(;;){if(p=g>>>24,f>>>=p,c-=p,p=g>>>16&255,!(16&p)){if(0==(64&p)){g=w[(65535&g)+(f&(1<<p)-1)];continue a}t.msg="invalid distance code",E.mode=16209;break t}if(v=65535&g,p&=15,c<p&&(f+=z[a++]<<c,c+=8,c<p&&(f+=z[a++]<<c,c+=8)),v+=f&(1<<p)-1,v>o){t.msg="invalid distance too far back",E.mode=16209;break t}if(f>>>=p,c-=p,p=n-s,v>p){if(p=v-p,p>h&&E.sane){t.msg="invalid distance too far back",E.mode=16209;break t}if(y=0,x=_,0===d){if(y+=l-p,p<k){k-=p;do{A[n++]=_[y++]}while(--p);y=n-v,x=A}}else if(d<p){if(y+=l+d-p,p-=d,p<k){k-=p;do{A[n++]=_[y++]}while(--p);if(y=0,d<k){p=d,k-=p;do{A[n++]=_[y++]}while(--p);y=n-v,x=A}}}else if(y+=d-p,p<k){k-=p;do{A[n++]=_[y++]}while(--p);y=n-v,x=A}for(;k>2;)A[n++]=x[y++],A[n++]=x[y++],A[n++]=x[y++],k-=3;k&&(A[n++]=x[y++],k>1&&(A[n++]=x[y++]))}else{y=n-v;do{A[n++]=A[y++],A[n++]=A[y++],A[n++]=A[y++],k-=3}while(k>2);k&&(A[n++]=A[y++],k>1&&(A[n++]=A[y++]))}break}}break}}while(a<i&&n<r);k=c>>3,a-=k,c-=k<<3,f&=(1<<c)-1,t.next_in=a,t.next_out=n,t.avail_in=a<i?i-a+5:5-(a-i),t.avail_out=n<r?r-n+257:257-(n-r),E.hold=f,E.bits=c};const te=new Uint16Array([3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258,0,0]),ee=new Uint8Array([16,16,16,16,16,16,16,16,17,17,17,17,18,18,18,18,19,19,19,19,20,20,20,20,21,21,21,21,16,72,78]),ae=new Uint16Array([1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577,0,0]),ie=new Uint8Array([16,16,16,16,17,17,18,18,19,19,20,20,21,21,22,22,23,23,24,24,25,25,26,26,27,27,28,28,29,29,64,64]);var ne=(t,e,a,i,n,s,r,o)=>{const l=o.bits;let h,d,_,f,c,u,w=0,m=0,b=0,g=0,p=0,k=0,v=0,y=0,x=0,z=0,A=null;const E=new Uint16Array(16),R=new Uint16Array(16);let Z,S,U,D=null;for(w=0;w<=15;w++)E[w]=0;for(m=0;m<i;m++)E[e[a+m]]++;for(p=l,g=15;g>=1&&0===E[g];g--);if(p>g&&(p=g),0===g)return n[s++]=20971520,n[s++]=20971520,o.bits=1,0;for(b=1;b<g&&0===E[b];b++);for(p<b&&(p=b),y=1,w=1;w<=15;w++)if(y<<=1,y-=E[w],y<0)return-1;if(y>0&&(0===t||1!==g))return-1;for(R[1]=0,w=1;w<15;w++)R[w+1]=R[w]+E[w];for(m=0;m<i;m++)0!==e[a+m]&&(r[R[e[a+m]]++]=m);if(0===t?(A=D=r,u=20):1===t?(A=te,D=ee,u=257):(A=ae,D=ie,u=0),z=0,m=0,w=b,c=s,k=p,v=0,_=-1,x=1<<p,f=x-1,1===t&&x>852||2===t&&x>592)return 1;for(;;){Z=w-v,r[m]+1<u?(S=0,U=r[m]):r[m]>=u?(S=D[r[m]-u],U=A[r[m]-u]):(S=96,U=0),h=1<<w-v,d=1<<k,b=d;do{d-=h,n[c+(z>>v)+d]=Z<<24|S<<16|U|0}while(0!==d);for(h=1<<w-1;z&h;)h>>=1;if(0!==h?(z&=h-1,z+=h):z=0,m++,0==--E[w]){if(w===g)break;w=e[a+r[m]]}if(w>p&&(z&f)!==_){for(0===v&&(v=p),c+=b,k=w-v,y=1<<k;k+v<g&&(y-=E[k+v],!(y<=0));)k++,y<<=1;if(x+=1<<k,1===t&&x>852||2===t&&x>592)return 1;_=z&f,n[_]=p<<24|k<<16|c-s|0}}return 0!==z&&(n[c+z]=w-v<<24|64<<16|0),o.bits=p,0};const{Z_FINISH:se,Z_BLOCK:re,Z_TREES:oe,Z_OK:le,Z_STREAM_END:he,Z_NEED_DICT:de,Z_STREAM_ERROR:_e,Z_DATA_ERROR:fe,Z_MEM_ERROR:ce,Z_BUF_ERROR:ue,Z_DEFLATED:we}=B,me=16209,be=t=>(t>>>24&255)+(t>>>8&65280)+((65280&t)<<8)+((255&t)<<24);function ge(){this.strm=null,this.mode=0,this.last=!1,this.wrap=0,this.havedict=!1,this.flags=0,this.dmax=0,this.check=0,this.total=0,this.head=null,this.wbits=0,this.wsize=0,this.whave=0,this.wnext=0,this.window=null,this.hold=0,this.bits=0,this.length=0,this.offset=0,this.extra=0,this.lencode=null,this.distcode=null,this.lenbits=0,this.distbits=0,this.ncode=0,this.nlen=0,this.ndist=0,this.have=0,this.next=null,this.lens=new Uint16Array(320),this.work=new Uint16Array(288),this.lendyn=null,this.distdyn=null,this.sane=0,this.back=0,this.was=0}const pe=t=>{if(!t)return 1;const e=t.state;return!e||e.strm!==t||e.mode<16180||e.mode>16211?1:0},ke=t=>{if(pe(t))return _e;const e=t.state;return t.total_in=t.total_out=e.total=0,t.msg="",e.wrap&&(t.adler=1&e.wrap),e.mode=16180,e.last=0,e.havedict=0,e.flags=-1,e.dmax=32768,e.head=null,e.hold=0,e.bits=0,e.lencode=e.lendyn=new Int32Array(852),e.distcode=e.distdyn=new Int32Array(592),e.sane=1,e.back=-1,le},ve=t=>{if(pe(t))return _e;const e=t.state;return e.wsize=0,e.whave=0,e.wnext=0,ke(t)},ye=(t,e)=>{let a;if(pe(t))return _e;const i=t.state;return e<0?(a=0,e=-e):(a=5+(e>>4),e<48&&(e&=15)),e&&(e<8||e>15)?_e:(null!==i.window&&i.wbits!==e&&(i.window=null),i.wrap=a,i.wbits=e,ve(t))},xe=(t,e)=>{if(!t)return _e;const a=new ge;t.state=a,a.strm=t,a.window=null,a.mode=16180;const i=ye(t,e);return i!==le&&(t.state=null),i};let ze,Ae,Ee=!0;const Re=t=>{if(Ee){ze=new Int32Array(512),Ae=new Int32Array(32);let e=0;for(;e<144;)t.lens[e++]=8;for(;e<256;)t.lens[e++]=9;for(;e<280;)t.lens[e++]=7;for(;e<288;)t.lens[e++]=8;for(ne(1,t.lens,0,288,ze,0,t.work,{bits:9}),e=0;e<32;)t.lens[e++]=5;ne(2,t.lens,0,32,Ae,0,t.work,{bits:5}),Ee=!1}t.lencode=ze,t.lenbits=9,t.distcode=Ae,t.distbits=5},Ze=(t,e,a,i)=>{let n;const s=t.state;return null===s.window&&(s.wsize=1<<s.wbits,s.wnext=0,s.whave=0,s.window=new Uint8Array(s.wsize)),i>=s.wsize?(s.window.set(e.subarray(a-s.wsize,a),0),s.wnext=0,s.whave=s.wsize):(n=s.wsize-s.wnext,n>i&&(n=i),s.window.set(e.subarray(a-i,a-i+n),s.wnext),(i-=n)?(s.window.set(e.subarray(a-i,a),0),s.wnext=i,s.whave=s.wsize):(s.wnext+=n,s.wnext===s.wsize&&(s.wnext=0),s.whave<s.wsize&&(s.whave+=n))),0};var Se={inflateReset:ve,inflateReset2:ye,inflateResetKeep:ke,inflateInit:t=>xe(t,15),inflateInit2:xe,inflate:(t,e)=>{let a,i,n,s,r,o,l,h,d,_,f,c,u,w,m,b,g,p,k,v,y,x,z=0;const A=new Uint8Array(4);let E,R;const Z=new Uint8Array([16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15]);if(pe(t)||!t.output||!t.input&&0!==t.avail_in)return _e;a=t.state,16191===a.mode&&(a.mode=16192),r=t.next_out,n=t.output,l=t.avail_out,s=t.next_in,i=t.input,o=t.avail_in,h=a.hold,d=a.bits,_=o,f=l,x=le;t:for(;;)switch(a.mode){case 16180:if(0===a.wrap){a.mode=16192;break}for(;d<16;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(2&a.wrap&&35615===h){0===a.wbits&&(a.wbits=15),a.check=0,A[0]=255&h,A[1]=h>>>8&255,a.check=L(a.check,A,2,0),h=0,d=0,a.mode=16181;break}if(a.head&&(a.head.done=!1),!(1&a.wrap)||(((255&h)<<8)+(h>>8))%31){t.msg="incorrect header check",a.mode=me;break}if((15&h)!==we){t.msg="unknown compression method",a.mode=me;break}if(h>>>=4,d-=4,y=8+(15&h),0===a.wbits&&(a.wbits=y),y>15||y>a.wbits){t.msg="invalid window size",a.mode=me;break}a.dmax=1<<a.wbits,a.flags=0,t.adler=a.check=1,a.mode=512&h?16189:16191,h=0,d=0;break;case 16181:for(;d<16;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(a.flags=h,(255&a.flags)!==we){t.msg="unknown compression method",a.mode=me;break}if(57344&a.flags){t.msg="unknown header flags set",a.mode=me;break}a.head&&(a.head.text=h>>8&1),512&a.flags&&4&a.wrap&&(A[0]=255&h,A[1]=h>>>8&255,a.check=L(a.check,A,2,0)),h=0,d=0,a.mode=16182;case 16182:for(;d<32;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}a.head&&(a.head.time=h),512&a.flags&&4&a.wrap&&(A[0]=255&h,A[1]=h>>>8&255,A[2]=h>>>16&255,A[3]=h>>>24&255,a.check=L(a.check,A,4,0)),h=0,d=0,a.mode=16183;case 16183:for(;d<16;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}a.head&&(a.head.xflags=255&h,a.head.os=h>>8),512&a.flags&&4&a.wrap&&(A[0]=255&h,A[1]=h>>>8&255,a.check=L(a.check,A,2,0)),h=0,d=0,a.mode=16184;case 16184:if(1024&a.flags){for(;d<16;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}a.length=h,a.head&&(a.head.extra_len=h),512&a.flags&&4&a.wrap&&(A[0]=255&h,A[1]=h>>>8&255,a.check=L(a.check,A,2,0)),h=0,d=0}else a.head&&(a.head.extra=null);a.mode=16185;case 16185:if(1024&a.flags&&(c=a.length,c>o&&(c=o),c&&(a.head&&(y=a.head.extra_len-a.length,a.head.extra||(a.head.extra=new Uint8Array(a.head.extra_len)),a.head.extra.set(i.subarray(s,s+c),y)),512&a.flags&&4&a.wrap&&(a.check=L(a.check,i,c,s)),o-=c,s+=c,a.length-=c),a.length))break t;a.length=0,a.mode=16186;case 16186:if(2048&a.flags){if(0===o)break t;c=0;do{y=i[s+c++],a.head&&y&&a.length<65536&&(a.head.name+=String.fromCharCode(y))}while(y&&c<o);if(512&a.flags&&4&a.wrap&&(a.check=L(a.check,i,c,s)),o-=c,s+=c,y)break t}else a.head&&(a.head.name=null);a.length=0,a.mode=16187;case 16187:if(4096&a.flags){if(0===o)break t;c=0;do{y=i[s+c++],a.head&&y&&a.length<65536&&(a.head.comment+=String.fromCharCode(y))}while(y&&c<o);if(512&a.flags&&4&a.wrap&&(a.check=L(a.check,i,c,s)),o-=c,s+=c,y)break t}else a.head&&(a.head.comment=null);a.mode=16188;case 16188:if(512&a.flags){for(;d<16;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(4&a.wrap&&h!==(65535&a.check)){t.msg="header crc mismatch",a.mode=me;break}h=0,d=0}a.head&&(a.head.hcrc=a.flags>>9&1,a.head.done=!0),t.adler=a.check=0,a.mode=16191;break;case 16189:for(;d<32;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}t.adler=a.check=be(h),h=0,d=0,a.mode=16190;case 16190:if(0===a.havedict)return t.next_out=r,t.avail_out=l,t.next_in=s,t.avail_in=o,a.hold=h,a.bits=d,de;t.adler=a.check=1,a.mode=16191;case 16191:if(e===re||e===oe)break t;case 16192:if(a.last){h>>>=7&d,d-=7&d,a.mode=16206;break}for(;d<3;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}switch(a.last=1&h,h>>>=1,d-=1,3&h){case 0:a.mode=16193;break;case 1:if(Re(a),a.mode=16199,e===oe){h>>>=2,d-=2;break t}break;case 2:a.mode=16196;break;case 3:t.msg="invalid block type",a.mode=me}h>>>=2,d-=2;break;case 16193:for(h>>>=7&d,d-=7&d;d<32;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if((65535&h)!=(h>>>16^65535)){t.msg="invalid stored block lengths",a.mode=me;break}if(a.length=65535&h,h=0,d=0,a.mode=16194,e===oe)break t;case 16194:a.mode=16195;case 16195:if(c=a.length,c){if(c>o&&(c=o),c>l&&(c=l),0===c)break t;n.set(i.subarray(s,s+c),r),o-=c,s+=c,l-=c,r+=c,a.length-=c;break}a.mode=16191;break;case 16196:for(;d<14;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(a.nlen=257+(31&h),h>>>=5,d-=5,a.ndist=1+(31&h),h>>>=5,d-=5,a.ncode=4+(15&h),h>>>=4,d-=4,a.nlen>286||a.ndist>30){t.msg="too many length or distance symbols",a.mode=me;break}a.have=0,a.mode=16197;case 16197:for(;a.have<a.ncode;){for(;d<3;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}a.lens[Z[a.have++]]=7&h,h>>>=3,d-=3}for(;a.have<19;)a.lens[Z[a.have++]]=0;if(a.lencode=a.lendyn,a.lenbits=7,E={bits:a.lenbits},x=ne(0,a.lens,0,19,a.lencode,0,a.work,E),a.lenbits=E.bits,x){t.msg="invalid code lengths set",a.mode=me;break}a.have=0,a.mode=16198;case 16198:for(;a.have<a.nlen+a.ndist;){for(;z=a.lencode[h&(1<<a.lenbits)-1],m=z>>>24,b=z>>>16&255,g=65535&z,!(m<=d);){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(g<16)h>>>=m,d-=m,a.lens[a.have++]=g;else{if(16===g){for(R=m+2;d<R;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(h>>>=m,d-=m,0===a.have){t.msg="invalid bit length repeat",a.mode=me;break}y=a.lens[a.have-1],c=3+(3&h),h>>>=2,d-=2}else if(17===g){for(R=m+3;d<R;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}h>>>=m,d-=m,y=0,c=3+(7&h),h>>>=3,d-=3}else{for(R=m+7;d<R;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}h>>>=m,d-=m,y=0,c=11+(127&h),h>>>=7,d-=7}if(a.have+c>a.nlen+a.ndist){t.msg="invalid bit length repeat",a.mode=me;break}for(;c--;)a.lens[a.have++]=y}}if(a.mode===me)break;if(0===a.lens[256]){t.msg="invalid code -- missing end-of-block",a.mode=me;break}if(a.lenbits=9,E={bits:a.lenbits},x=ne(1,a.lens,0,a.nlen,a.lencode,0,a.work,E),a.lenbits=E.bits,x){t.msg="invalid literal/lengths set",a.mode=me;break}if(a.distbits=6,a.distcode=a.distdyn,E={bits:a.distbits},x=ne(2,a.lens,a.nlen,a.ndist,a.distcode,0,a.work,E),a.distbits=E.bits,x){t.msg="invalid distances set",a.mode=me;break}if(a.mode=16199,e===oe)break t;case 16199:a.mode=16200;case 16200:if(o>=6&&l>=258){t.next_out=r,t.avail_out=l,t.next_in=s,t.avail_in=o,a.hold=h,a.bits=d,$t(t,f),r=t.next_out,n=t.output,l=t.avail_out,s=t.next_in,i=t.input,o=t.avail_in,h=a.hold,d=a.bits,16191===a.mode&&(a.back=-1);break}for(a.back=0;z=a.lencode[h&(1<<a.lenbits)-1],m=z>>>24,b=z>>>16&255,g=65535&z,!(m<=d);){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(b&&0==(240&b)){for(p=m,k=b,v=g;z=a.lencode[v+((h&(1<<p+k)-1)>>p)],m=z>>>24,b=z>>>16&255,g=65535&z,!(p+m<=d);){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}h>>>=p,d-=p,a.back+=p}if(h>>>=m,d-=m,a.back+=m,a.length=g,0===b){a.mode=16205;break}if(32&b){a.back=-1,a.mode=16191;break}if(64&b){t.msg="invalid literal/length code",a.mode=me;break}a.extra=15&b,a.mode=16201;case 16201:if(a.extra){for(R=a.extra;d<R;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}a.length+=h&(1<<a.extra)-1,h>>>=a.extra,d-=a.extra,a.back+=a.extra}a.was=a.length,a.mode=16202;case 16202:for(;z=a.distcode[h&(1<<a.distbits)-1],m=z>>>24,b=z>>>16&255,g=65535&z,!(m<=d);){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(0==(240&b)){for(p=m,k=b,v=g;z=a.distcode[v+((h&(1<<p+k)-1)>>p)],m=z>>>24,b=z>>>16&255,g=65535&z,!(p+m<=d);){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}h>>>=p,d-=p,a.back+=p}if(h>>>=m,d-=m,a.back+=m,64&b){t.msg="invalid distance code",a.mode=me;break}a.offset=g,a.extra=15&b,a.mode=16203;case 16203:if(a.extra){for(R=a.extra;d<R;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}a.offset+=h&(1<<a.extra)-1,h>>>=a.extra,d-=a.extra,a.back+=a.extra}if(a.offset>a.dmax){t.msg="invalid distance too far back",a.mode=me;break}a.mode=16204;case 16204:if(0===l)break t;if(c=f-l,a.offset>c){if(c=a.offset-c,c>a.whave&&a.sane){t.msg="invalid distance too far back",a.mode=me;break}c>a.wnext?(c-=a.wnext,u=a.wsize-c):u=a.wnext-c,c>a.length&&(c=a.length),w=a.window}else w=n,u=r-a.offset,c=a.length;c>l&&(c=l),l-=c,a.length-=c;do{n[r++]=w[u++]}while(--c);0===a.length&&(a.mode=16200);break;case 16205:if(0===l)break t;n[r++]=a.length,l--,a.mode=16200;break;case 16206:if(a.wrap){for(;d<32;){if(0===o)break t;o--,h|=i[s++]<<d,d+=8}if(f-=l,t.total_out+=f,a.total+=f,4&a.wrap&&f&&(t.adler=a.check=a.flags?L(a.check,n,f,r-f):N(a.check,n,f,r-f)),f=l,4&a.wrap&&(a.flags?h:be(h))!==a.check){t.msg="incorrect data check",a.mode=me;break}h=0,d=0}a.mode=16207;case 16207:if(a.wrap&&a.flags){for(;d<32;){if(0===o)break t;o--,h+=i[s++]<<d,d+=8}if(4&a.wrap&&h!==(4294967295&a.total)){t.msg="incorrect length check",a.mode=me;break}h=0,d=0}a.mode=16208;case 16208:x=he;break t;case me:x=fe;break t;case 16210:return ce;default:return _e}return t.next_out=r,t.avail_out=l,t.next_in=s,t.avail_in=o,a.hold=h,a.bits=d,(a.wsize||f!==t.avail_out&&a.mode<me&&(a.mode<16206||e!==se))&&Ze(t,t.output,t.next_out,f-t.avail_out),_-=t.avail_in,f-=t.avail_out,t.total_in+=_,t.total_out+=f,a.total+=f,4&a.wrap&&f&&(t.adler=a.check=a.flags?L(a.check,n,f,t.next_out-f):N(a.check,n,f,t.next_out-f)),t.data_type=a.bits+(a.last?64:0)+(16191===a.mode?128:0)+(16199===a.mode||16194===a.mode?256:0),(0===_&&0===f||e===se)&&x===le&&(x=ue),x},inflateEnd:t=>{if(pe(t))return _e;let e=t.state;return e.window&&(e.window=null),t.state=null,le},inflateGetHeader:(t,e)=>{if(pe(t))return _e;const a=t.state;return 0==(2&a.wrap)?_e:(a.head=e,e.done=!1,le)},inflateSetDictionary:(t,e)=>{const a=e.length;let i,n,s;return pe(t)?_e:(i=t.state,0!==i.wrap&&16190!==i.mode?_e:16190===i.mode&&(n=1,n=N(n,e,a,0),n!==i.check)?fe:(s=Ze(t,e,a,a),s?(i.mode=16210,ce):(i.havedict=1,le)))},inflateInfo:"pako inflate (from Nodeca project)"};var Ue=function(){this.text=0,this.time=0,this.xflags=0,this.os=0,this.extra=null,this.extra_len=0,this.name="",this.comment="",this.hcrc=0,this.done=!1};const De=Object.prototype.toString,{Z_NO_FLUSH:Oe,Z_FINISH:Te,Z_OK:Ne,Z_STREAM_END:Fe,Z_NEED_DICT:Le,Z_STREAM_ERROR:Ie,Z_DATA_ERROR:Be,Z_MEM_ERROR:Ce}=B;function He(t){this.options=Ot({chunkSize:65536,windowBits:15,to:""},t||{});const e=this.options;e.raw&&e.windowBits>=0&&e.windowBits<16&&(e.windowBits=-e.windowBits,0===e.windowBits&&(e.windowBits=-15)),!(e.windowBits>=0&&e.windowBits<16)||t&&t.windowBits||(e.windowBits+=32),e.windowBits>15&&e.windowBits<48&&0==(15&e.windowBits)&&(e.windowBits|=15),this.err=0,this.msg="",this.ended=!1,this.chunks=[],this.strm=new Ct,this.strm.avail_out=0;let a=Se.inflateInit2(this.strm,e.windowBits);if(a!==Ne)throw new Error(I[a]);if(this.header=new Ue,Se.inflateGetHeader(this.strm,this.header),e.dictionary&&("string"==typeof e.dictionary?e.dictionary=Lt(e.dictionary):"[object ArrayBuffer]"===De.call(e.dictionary)&&(e.dictionary=new Uint8Array(e.dictionary)),e.raw&&(a=Se.inflateSetDictionary(this.strm,e.dictionary),a!==Ne)))throw new Error(I[a])}He.prototype.push=function(t,e){const a=this.strm,i=this.options.chunkSize,n=this.options.dictionary;let s,r,o;if(this.ended)return!1;for(r=e===~~e?e:!0===e?Te:Oe,"[object ArrayBuffer]"===De.call(t)?a.input=new Uint8Array(t):a.input=t,a.next_in=0,a.avail_in=a.input.length;;){for(0===a.avail_out&&(a.output=new Uint8Array(i),a.next_out=0,a.avail_out=i),s=Se.inflate(a,r),s===Le&&n&&(s=Se.inflateSetDictionary(a,n),s===Ne?s=Se.inflate(a,r):s===Be&&(s=Le));a.avail_in>0&&s===Fe&&a.state.wrap>0&&0!==t[a.next_in];)Se.inflateReset(a),s=Se.inflate(a,r);switch(s){case Ie:case Be:case Le:case Ce:return this.onEnd(s),this.ended=!0,!1}if(o=a.avail_out,a.next_out&&(0===a.avail_out||s===Fe))if("string"===this.options.to){let t=Bt(a.output,a.next_out),e=a.next_out-t,n=It(a.output,t);a.next_out=e,a.avail_out=i-e,e&&a.output.set(a.output.subarray(t,t+e),0),this.onData(n)}else this.onData(a.output.length===a.next_out?a.output:a.output.subarray(0,a.next_out));if(s!==Ne||0!==o){if(s===Fe)return s=Se.inflateEnd(this.strm),this.onEnd(s),this.ended=!0,!0;if(0===a.avail_in)break}}return!0},He.prototype.onData=function(t){this.chunks.push(t)},He.prototype.onEnd=function(t){t===Ne&&("string"===this.options.to?this.result=this.chunks.join(""):this.result=Tt(this.chunks)),this.chunks=[],this.err=t,this.msg=this.strm.msg};const{Deflate:Me,deflate:je,deflateRaw:Ke,gzip:Pe}=Vt;var Ye=Me,Ge=B;const Xe=new class{constructor(){this.added=0,this.init()}init(){this.added=0,this.deflate=new Ye,this.deflate.push("[",Ge.Z_NO_FLUSH)}addEvent(t){if(!t)return;const e=this.added>0?",":"";this.deflate.push(e+JSON.stringify(t),Ge.Z_NO_FLUSH),this.added++}finish(){if(this.deflate.push("]",Ge.Z_FINISH),this.deflate.err)throw this.deflate.err;const t=this.deflate.result;return this.init(),t}},Je={init:()=>(Xe.init(),""),addEvent:t=>(Xe.addEvent(t),""),finish:()=>Xe.finish()};addEventListener("message",(function(t){const e=t.data.method,a=t.data.id,[i]=t.data.args?JSON.parse(t.data.args):[];if(e in Je&&"function"==typeof Je[e])try{const t=Je[e](i);postMessage({id:a,method:e,success:!0,response:t})}catch(t){postMessage({id:a,method:e,success:!1,response:t}),console.error(t)}}));`;

exports.default = workerString;


},{}],109:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');
const logger = require('./logger.js');

const BAGGAGE_HEADER_NAME = 'baggage';

const SENTRY_BAGGAGE_KEY_PREFIX = 'sentry-';

const SENTRY_BAGGAGE_KEY_PREFIX_REGEX = /^sentry-/;

/**
 * Max length of a serialized baggage string
 *
 * https://www.w3.org/TR/baggage/#limits
 */
const MAX_BAGGAGE_STRING_LENGTH = 8192;

/**
 * Takes a baggage header and turns it into Dynamic Sampling Context, by extracting all the "sentry-" prefixed values
 * from it.
 *
 * @param baggageHeader A very bread definition of a baggage header as it might appear in various frameworks.
 * @returns The Dynamic Sampling Context that was found on `baggageHeader`, if there was any, `undefined` otherwise.
 */
function baggageHeaderToDynamicSamplingContext(
  // Very liberal definition of what any incoming header might look like
  baggageHeader,
) {
  if (!is.isString(baggageHeader) && !Array.isArray(baggageHeader)) {
    return undefined;
  }

  // Intermediary object to store baggage key value pairs of incoming baggage headers on.
  // It is later used to read Sentry-DSC-values from.
  let baggageObject = {};

  if (Array.isArray(baggageHeader)) {
    // Combine all baggage headers into one object containing the baggage values so we can later read the Sentry-DSC-values from it
    baggageObject = baggageHeader.reduce((acc, curr) => {
      const currBaggageObject = baggageHeaderToObject(curr);
      return {
        ...acc,
        ...currBaggageObject,
      };
    }, {});
  } else {
    // Return undefined if baggage header is an empty string (technically an empty baggage header is not spec conform but
    // this is how we choose to handle it)
    if (!baggageHeader) {
      return undefined;
    }

    baggageObject = baggageHeaderToObject(baggageHeader);
  }

  // Read all "sentry-" prefixed values out of the baggage object and put it onto a dynamic sampling context object.
  const dynamicSamplingContext = Object.entries(baggageObject).reduce((acc, [key, value]) => {
    if (key.match(SENTRY_BAGGAGE_KEY_PREFIX_REGEX)) {
      const nonPrefixedKey = key.slice(SENTRY_BAGGAGE_KEY_PREFIX.length);
      acc[nonPrefixedKey] = value;
    }
    return acc;
  }, {});

  // Only return a dynamic sampling context object if there are keys in it.
  // A keyless object means there were no sentry values on the header, which means that there is no DSC.
  if (Object.keys(dynamicSamplingContext).length > 0) {
    return dynamicSamplingContext ;
  } else {
    return undefined;
  }
}

/**
 * Turns a Dynamic Sampling Object into a baggage header by prefixing all the keys on the object with "sentry-".
 *
 * @param dynamicSamplingContext The Dynamic Sampling Context to turn into a header. For convenience and compatibility
 * with the `getDynamicSamplingContext` method on the Transaction class ,this argument can also be `undefined`. If it is
 * `undefined` the function will return `undefined`.
 * @returns a baggage header, created from `dynamicSamplingContext`, or `undefined` either if `dynamicSamplingContext`
 * was `undefined`, or if `dynamicSamplingContext` didn't contain any values.
 */
function dynamicSamplingContextToSentryBaggageHeader(
  // this also takes undefined for convenience and bundle size in other places
  dynamicSamplingContext,
) {
  // Prefix all DSC keys with "sentry-" and put them into a new object
  const sentryPrefixedDSC = Object.entries(dynamicSamplingContext).reduce(
    (acc, [dscKey, dscValue]) => {
      if (dscValue) {
        acc[`${SENTRY_BAGGAGE_KEY_PREFIX}${dscKey}`] = dscValue;
      }
      return acc;
    },
    {},
  );

  return objectToBaggageHeader(sentryPrefixedDSC);
}

/**
 * Will parse a baggage header, which is a simple key-value map, into a flat object.
 *
 * @param baggageHeader The baggage header to parse.
 * @returns a flat object containing all the key-value pairs from `baggageHeader`.
 */
function baggageHeaderToObject(baggageHeader) {
  return baggageHeader
    .split(',')
    .map(baggageEntry => baggageEntry.split('=').map(keyOrValue => decodeURIComponent(keyOrValue.trim())))
    .reduce((acc, [key, value]) => {
      acc[key] = value;
      return acc;
    }, {});
}

/**
 * Turns a flat object (key-value pairs) into a baggage header, which is also just key-value pairs.
 *
 * @param object The object to turn into a baggage header.
 * @returns a baggage header string, or `undefined` if the object didn't have any values, since an empty baggage header
 * is not spec compliant.
 */
function objectToBaggageHeader(object) {
  if (Object.keys(object).length === 0) {
    // An empty baggage header is not spec compliant: We return undefined.
    return undefined;
  }

  return Object.entries(object).reduce((baggageHeader, [objectKey, objectValue], currentIndex) => {
    const baggageEntry = `${encodeURIComponent(objectKey)}=${encodeURIComponent(objectValue)}`;
    const newBaggageHeader = currentIndex === 0 ? baggageEntry : `${baggageHeader},${baggageEntry}`;
    if (newBaggageHeader.length > MAX_BAGGAGE_STRING_LENGTH) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
        logger.logger.warn(
          `Not adding key: ${objectKey} with val: ${objectValue} to baggage header due to exceeding baggage size limits.`,
        );
      return baggageHeader;
    } else {
      return newBaggageHeader;
    }
  }, '');
}

exports.BAGGAGE_HEADER_NAME = BAGGAGE_HEADER_NAME;
exports.MAX_BAGGAGE_STRING_LENGTH = MAX_BAGGAGE_STRING_LENGTH;
exports.SENTRY_BAGGAGE_KEY_PREFIX = SENTRY_BAGGAGE_KEY_PREFIX;
exports.SENTRY_BAGGAGE_KEY_PREFIX_REGEX = SENTRY_BAGGAGE_KEY_PREFIX_REGEX;
exports.baggageHeaderToDynamicSamplingContext = baggageHeaderToDynamicSamplingContext;
exports.dynamicSamplingContextToSentryBaggageHeader = dynamicSamplingContextToSentryBaggageHeader;


},{"./is.js":132,"./logger.js":133}],110:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');
const worldwide = require('./worldwide.js');

// eslint-disable-next-line deprecation/deprecation
const WINDOW = worldwide.getGlobalObject();

const DEFAULT_MAX_STRING_LENGTH = 80;

/**
 * Given a child DOM element, returns a query-selector statement describing that
 * and its ancestors
 * e.g. [HTMLElement] => body > div > input#foo.btn[name=baz]
 * @returns generated DOM path
 */
function htmlTreeAsString(
  elem,
  options = {},
) {

  // try/catch both:
  // - accessing event.target (see getsentry/raven-js#838, #768)
  // - `htmlTreeAsString` because it's complex, and just accessing the DOM incorrectly
  // - can throw an exception in some circumstances.
  try {
    let currentElem = elem ;
    const MAX_TRAVERSE_HEIGHT = 5;
    const out = [];
    let height = 0;
    let len = 0;
    const separator = ' > ';
    const sepLength = separator.length;
    let nextStr;
    const keyAttrs = Array.isArray(options) ? options : options.keyAttrs;
    const maxStringLength = (!Array.isArray(options) && options.maxStringLength) || DEFAULT_MAX_STRING_LENGTH;

    while (currentElem && height++ < MAX_TRAVERSE_HEIGHT) {
      nextStr = _htmlElementAsString(currentElem, keyAttrs);
      // bail out if
      // - nextStr is the 'html' element
      // - the length of the string that would be created exceeds maxStringLength
      //   (ignore this limit if we are on the first iteration)
      if (nextStr === 'html' || (height > 1 && len + out.length * sepLength + nextStr.length >= maxStringLength)) {
        break;
      }

      out.push(nextStr);

      len += nextStr.length;
      currentElem = currentElem.parentNode;
    }

    return out.reverse().join(separator);
  } catch (_oO) {
    return '<unknown>';
  }
}

/**
 * Returns a simple, query-selector representation of a DOM element
 * e.g. [HTMLElement] => input#foo.btn[name=baz]
 * @returns generated DOM path
 */
function _htmlElementAsString(el, keyAttrs) {
  const elem = el

;

  const out = [];
  let className;
  let classes;
  let key;
  let attr;
  let i;

  if (!elem || !elem.tagName) {
    return '';
  }

  out.push(elem.tagName.toLowerCase());

  // Pairs of attribute keys defined in `serializeAttribute` and their values on element.
  const keyAttrPairs =
    keyAttrs && keyAttrs.length
      ? keyAttrs.filter(keyAttr => elem.getAttribute(keyAttr)).map(keyAttr => [keyAttr, elem.getAttribute(keyAttr)])
      : null;

  if (keyAttrPairs && keyAttrPairs.length) {
    keyAttrPairs.forEach(keyAttrPair => {
      out.push(`[${keyAttrPair[0]}="${keyAttrPair[1]}"]`);
    });
  } else {
    if (elem.id) {
      out.push(`#${elem.id}`);
    }

    // eslint-disable-next-line prefer-const
    className = elem.className;
    if (className && is.isString(className)) {
      classes = className.split(/\s+/);
      for (i = 0; i < classes.length; i++) {
        out.push(`.${classes[i]}`);
      }
    }
  }
  const allowedAttrs = ['type', 'name', 'title', 'alt'];
  for (i = 0; i < allowedAttrs.length; i++) {
    key = allowedAttrs[i];
    attr = elem.getAttribute(key);
    if (attr) {
      out.push(`[${key}="${attr}"]`);
    }
  }
  return out.join('');
}

/**
 * A safe form of location.href
 */
function getLocationHref() {
  try {
    return WINDOW.document.location.href;
  } catch (oO) {
    return '';
  }
}

/**
 * Gets a DOM element by using document.querySelector.
 *
 * This wrapper will first check for the existance of the function before
 * actually calling it so that we don't have to take care of this check,
 * every time we want to access the DOM.
 *
 * Reason: DOM/querySelector is not available in all environments.
 *
 * We have to cast to any because utils can be consumed by a variety of environments,
 * and we don't want to break TS users. If you know what element will be selected by
 * `document.querySelector`, specify it as part of the generic call. For example,
 * `const element = getDomElement<Element>('selector');`
 *
 * @param selector the selector string passed on to document.querySelector
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getDomElement(selector) {
  if (WINDOW.document && WINDOW.document.querySelector) {
    return WINDOW.document.querySelector(selector) ;
  }
  return null;
}

exports.getDomElement = getDomElement;
exports.getLocationHref = getLocationHref;
exports.htmlTreeAsString = htmlTreeAsString;


},{"./is.js":132,"./worldwide.js":151}],111:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _nullishCoalesce = require('./_nullishCoalesce.js');

// adapted from Sucrase (https://github.com/alangpierce/sucrase)

/**
 * Polyfill for the nullish coalescing operator (`??`), when used in situations where at least one of the values is the
 * result of an async operation.
 *
 * Note that the RHS is wrapped in a function so that if it's a computed value, that evaluation won't happen unless the
 * LHS evaluates to a nullish value, to mimic the operator's short-circuiting behavior.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase)
 *
 * @param lhs The value of the expression to the left of the `??`
 * @param rhsFn A function returning the value of the expression to the right of the `??`
 * @returns The LHS value, unless it's `null` or `undefined`, in which case, the RHS value
 */
// eslint-disable-next-line @sentry-internal/sdk/no-async-await
async function _asyncNullishCoalesce(lhs, rhsFn) {
  return _nullishCoalesce._nullishCoalesce(lhs, rhsFn);
}

// Sucrase version:
// async function _asyncNullishCoalesce(lhs, rhsFn) {
//   if (lhs != null) {
//     return lhs;
//   } else {
//     return await rhsFn();
//   }
// }

exports._asyncNullishCoalesce = _asyncNullishCoalesce;


},{"./_nullishCoalesce.js":121}],112:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Polyfill for the optional chain operator, `?.`, given previous conversion of the expression into an array of values,
 * descriptors, and functions, for situations in which at least one part of the expression is async.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase) See
 * https://github.com/alangpierce/sucrase/blob/265887868966917f3b924ce38dfad01fbab1329f/src/transformers/OptionalChainingNullishTransformer.ts#L15
 *
 * @param ops Array result of expression conversion
 * @returns The value of the expression
 */
// eslint-disable-next-line @sentry-internal/sdk/no-async-await
async function _asyncOptionalChain(ops) {
  let lastAccessLHS = undefined;
  let value = ops[0];
  let i = 1;
  while (i < ops.length) {
    const op = ops[i] ;
    const fn = ops[i + 1] ;
    i += 2;
    // by checking for loose equality to `null`, we catch both `null` and `undefined`
    if ((op === 'optionalAccess' || op === 'optionalCall') && value == null) {
      // really we're meaning to return `undefined` as an actual value here, but it saves bytes not to write it
      return;
    }
    if (op === 'access' || op === 'optionalAccess') {
      lastAccessLHS = value;
      value = await fn(value);
    } else if (op === 'call' || op === 'optionalCall') {
      value = await fn((...args) => (value ).call(lastAccessLHS, ...args));
      lastAccessLHS = undefined;
    }
  }
  return value;
}

// Sucrase version:
// async function _asyncOptionalChain(ops) {
//   let lastAccessLHS = undefined;
//   let value = ops[0];
//   let i = 1;
//   while (i < ops.length) {
//     const op = ops[i];
//     const fn = ops[i + 1];
//     i += 2;
//     if ((op === 'optionalAccess' || op === 'optionalCall') && value == null) {
//       return undefined;
//     }
//     if (op === 'access' || op === 'optionalAccess') {
//       lastAccessLHS = value;
//       value = await fn(value);
//     } else if (op === 'call' || op === 'optionalCall') {
//       value = await fn((...args) => value.call(lastAccessLHS, ...args));
//       lastAccessLHS = undefined;
//     }
//   }
//   return value;
// }

exports._asyncOptionalChain = _asyncOptionalChain;


},{}],113:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _asyncOptionalChain = require('./_asyncOptionalChain.js');

/**
 * Polyfill for the optional chain operator, `?.`, given previous conversion of the expression into an array of values,
 * descriptors, and functions, in cases where the value of the expression is to be deleted.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase) See
 * https://github.com/alangpierce/sucrase/blob/265887868966917f3b924ce38dfad01fbab1329f/src/transformers/OptionalChainingNullishTransformer.ts#L15
 *
 * @param ops Array result of expression conversion
 * @returns The return value of the `delete` operator: `true`, unless the deletion target is an own, non-configurable
 * property (one which can't be deleted or turned into an accessor, and whose enumerability can't be changed), in which
 * case `false`.
 */
// eslint-disable-next-line @sentry-internal/sdk/no-async-await
async function _asyncOptionalChainDelete(ops) {
  const result = (await _asyncOptionalChain._asyncOptionalChain(ops)) ;
  // If `result` is `null`, it means we didn't get to the end of the chain and so nothing was deleted (in which case,
  // return `true` since that's what `delete` does when it no-ops). If it's non-null, we know the delete happened, in
  // which case we return whatever the `delete` returned, which will be a boolean.
  return result == null ? true : (result );
}

// Sucrase version:
// async function asyncOptionalChainDelete(ops) {
//   const result = await ASYNC_OPTIONAL_CHAIN_NAME(ops);
//   return result == null ? true : result;
// }

exports._asyncOptionalChainDelete = _asyncOptionalChainDelete;


},{"./_asyncOptionalChain.js":112}],114:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Copy a property from the given object into `exports`, under the given name.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase)
 *
 * @param obj The object containing the property to copy.
 * @param localName The name under which to export the property
 * @param importedName The name under which the property lives in `obj`
 */
function _createNamedExportFrom(obj, localName, importedName) {
  exports[localName] = obj[importedName];
}

// Sucrase version:
// function _createNamedExportFrom(obj, localName, importedName) {
//   Object.defineProperty(exports, localName, {enumerable: true, get: () => obj[importedName]});
// }

exports._createNamedExportFrom = _createNamedExportFrom;


},{}],115:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Copy properties from an object into `exports`.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase)
 *
 * @param obj The object containing the properties to copy.
 */
function _createStarExport(obj) {
  Object.keys(obj)
    .filter(key => key !== 'default' && key !== '__esModule' && !(key in exports))
    .forEach(key => (exports[key] = obj[key]));
}

// Sucrase version:
// function _createStarExport(obj) {
//   Object.keys(obj)
//     .filter(key => key !== 'default' && key !== '__esModule')
//     .forEach(key => {
//       if (exports.hasOwnProperty(key)) {
//         return;
//       }
//       Object.defineProperty(exports, key, { enumerable: true, get: () => obj[key] });
//     });
// }

exports._createStarExport = _createStarExport;


},{}],116:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Unwraps a module if it has been wrapped in an object under the key `default`.
 *
 * Adapted from Rollup (https://github.com/rollup/rollup)
 *
 * @param requireResult The result of calling `require` on a module
 * @returns The full module, unwrapped if necessary.
 */
function _interopDefault$1(requireResult) {
  return requireResult.__esModule ? (requireResult.default ) : requireResult;
}

// Rollup version:
// function _interopDefault(e) {
//   return e && e.__esModule ? e['default'] : e;
// }

exports._interopDefault = _interopDefault$1;


},{}],117:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Adds a self-referential `default` property to CJS modules which aren't the result of transpilation from ESM modules.
 *
 * Adapted from Rollup (https://github.com/rollup/rollup)
 *
 * @param requireResult The result of calling `require` on a module
 * @returns Either `requireResult` or a copy of `requireResult` with an added self-referential `default` property
 */
function _interopNamespace$1(requireResult) {
  return requireResult.__esModule ? requireResult : { ...requireResult, default: requireResult };
}

// Rollup version (with `output.externalLiveBindings` and `output.freeze` both set to false)
// function _interopNamespace(e) {
//   if (e && e.__esModule) return e;
//   var n = Object.create(null);
//   if (e) {
//     for (var k in e) {
//       n[k] = e[k];
//     }
//   }
//   n["default"] = e;
//   return n;
// }

exports._interopNamespace = _interopNamespace$1;


},{}],118:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Wrap a module in an object, as the value under the key `default`.
 *
 * Adapted from Rollup (https://github.com/rollup/rollup)
 *
 * @param requireResult The result of calling `require` on a module
 * @returns An object containing the key-value pair (`default`, `requireResult`)
 */
function _interopNamespaceDefaultOnly$1(requireResult) {
  return {
    __proto__: null,
    default: requireResult,
  };
}

// Rollup version
// function _interopNamespaceDefaultOnly(e) {
//   return {
//     __proto__: null,
//     'default': e
//   };
// }

exports._interopNamespaceDefaultOnly = _interopNamespaceDefaultOnly$1;


},{}],119:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Wraps modules which aren't the result of transpiling an ESM module in an object under the key `default`
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase)
 *
 * @param requireResult The result of calling `require` on a module
 * @returns `requireResult` or `requireResult` wrapped in an object, keyed as `default`
 */
function _interopRequireDefault(requireResult) {
  return requireResult.__esModule ? requireResult : { default: requireResult };
}

// Sucrase version
// function _interopRequireDefault(obj) {
//   return obj && obj.__esModule ? obj : { default: obj };
// }

exports._interopRequireDefault = _interopRequireDefault;


},{}],120:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Adds a `default` property to CJS modules which aren't the result of transpilation from ESM modules.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase)
 *
 * @param requireResult The result of calling `require` on a module
 * @returns Either `requireResult` or a copy of `requireResult` with an added self-referential `default` property
 */
function _interopRequireWildcard(requireResult) {
  return requireResult.__esModule ? requireResult : { ...requireResult, default: requireResult };
}

// Sucrase version
// function _interopRequireWildcard(obj) {
//   if (obj && obj.__esModule) {
//     return obj;
//   } else {
//     var newObj = {};
//     if (obj != null) {
//       for (var key in obj) {
//         if (Object.prototype.hasOwnProperty.call(obj, key)) {
//           newObj[key] = obj[key];
//         }
//       }
//     }
//     newObj.default = obj;
//     return newObj;
//   }
// }

exports._interopRequireWildcard = _interopRequireWildcard;


},{}],121:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Polyfill for the nullish coalescing operator (`??`).
 *
 * Note that the RHS is wrapped in a function so that if it's a computed value, that evaluation won't happen unless the
 * LHS evaluates to a nullish value, to mimic the operator's short-circuiting behavior.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase)
 *
 * @param lhs The value of the expression to the left of the `??`
 * @param rhsFn A function returning the value of the expression to the right of the `??`
 * @returns The LHS value, unless it's `null` or `undefined`, in which case, the RHS value
 */
function _nullishCoalesce(lhs, rhsFn) {
  // by checking for loose equality to `null`, we catch both `null` and `undefined`
  return lhs != null ? lhs : rhsFn();
}

// Sucrase version:
// function _nullishCoalesce(lhs, rhsFn) {
//   if (lhs != null) {
//     return lhs;
//   } else {
//     return rhsFn();
//   }
// }

exports._nullishCoalesce = _nullishCoalesce;


},{}],122:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Polyfill for the optional chain operator, `?.`, given previous conversion of the expression into an array of values,
 * descriptors, and functions.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase)
 * See https://github.com/alangpierce/sucrase/blob/265887868966917f3b924ce38dfad01fbab1329f/src/transformers/OptionalChainingNullishTransformer.ts#L15
 *
 * @param ops Array result of expression conversion
 * @returns The value of the expression
 */
function _optionalChain(ops) {
  let lastAccessLHS = undefined;
  let value = ops[0];
  let i = 1;
  while (i < ops.length) {
    const op = ops[i] ;
    const fn = ops[i + 1] ;
    i += 2;
    // by checking for loose equality to `null`, we catch both `null` and `undefined`
    if ((op === 'optionalAccess' || op === 'optionalCall') && value == null) {
      // really we're meaning to return `undefined` as an actual value here, but it saves bytes not to write it
      return;
    }
    if (op === 'access' || op === 'optionalAccess') {
      lastAccessLHS = value;
      value = fn(value);
    } else if (op === 'call' || op === 'optionalCall') {
      value = fn((...args) => (value ).call(lastAccessLHS, ...args));
      lastAccessLHS = undefined;
    }
  }
  return value;
}

// Sucrase version
// function _optionalChain(ops) {
//   let lastAccessLHS = undefined;
//   let value = ops[0];
//   let i = 1;
//   while (i < ops.length) {
//     const op = ops[i];
//     const fn = ops[i + 1];
//     i += 2;
//     if ((op === 'optionalAccess' || op === 'optionalCall') && value == null) {
//       return undefined;
//     }
//     if (op === 'access' || op === 'optionalAccess') {
//       lastAccessLHS = value;
//       value = fn(value);
//     } else if (op === 'call' || op === 'optionalCall') {
//       value = fn((...args) => value.call(lastAccessLHS, ...args));
//       lastAccessLHS = undefined;
//     }
//   }
//   return value;
// }

exports._optionalChain = _optionalChain;


},{}],123:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _optionalChain = require('./_optionalChain.js');

/**
 * Polyfill for the optional chain operator, `?.`, given previous conversion of the expression into an array of values,
 * descriptors, and functions, in cases where the value of the expression is to be deleted.
 *
 * Adapted from Sucrase (https://github.com/alangpierce/sucrase) See
 * https://github.com/alangpierce/sucrase/blob/265887868966917f3b924ce38dfad01fbab1329f/src/transformers/OptionalChainingNullishTransformer.ts#L15
 *
 * @param ops Array result of expression conversion
 * @returns The return value of the `delete` operator: `true`, unless the deletion target is an own, non-configurable
 * property (one which can't be deleted or turned into an accessor, and whose enumerability can't be changed), in which
 * case `false`.
 */
function _optionalChainDelete(ops) {
  const result = _optionalChain._optionalChain(ops) ;
  // If `result` is `null`, it means we didn't get to the end of the chain and so nothing was deleted (in which case,
  // return `true` since that's what `delete` does when it no-ops). If it's non-null, we know the delete happened, in
  // which case we return whatever the `delete` returned, which will be a boolean.
  return result == null ? true : result;
}

// Sucrase version:
// function _optionalChainDelete(ops) {
//   const result = _optionalChain(ops);
//   // by checking for loose equality to `null`, we catch both `null` and `undefined`
//   return result == null ? true : result;
// }

exports._optionalChainDelete = _optionalChainDelete;


},{"./_optionalChain.js":122}],124:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _asyncNullishCoalesce = require('./_asyncNullishCoalesce.js');
const _asyncOptionalChain = require('./_asyncOptionalChain.js');
const _asyncOptionalChainDelete = require('./_asyncOptionalChainDelete.js');
const _createNamedExportFrom = require('./_createNamedExportFrom.js');
const _createStarExport = require('./_createStarExport.js');
const _interopDefault$1 = require('./_interopDefault.js');
const _interopNamespace$1 = require('./_interopNamespace.js');
const _interopNamespaceDefaultOnly$1 = require('./_interopNamespaceDefaultOnly.js');
const _interopRequireDefault = require('./_interopRequireDefault.js');
const _interopRequireWildcard = require('./_interopRequireWildcard.js');
const _nullishCoalesce = require('./_nullishCoalesce.js');
const _optionalChain = require('./_optionalChain.js');
const _optionalChainDelete = require('./_optionalChainDelete.js');



exports._asyncNullishCoalesce = _asyncNullishCoalesce._asyncNullishCoalesce;
exports._asyncOptionalChain = _asyncOptionalChain._asyncOptionalChain;
exports._asyncOptionalChainDelete = _asyncOptionalChainDelete._asyncOptionalChainDelete;
exports._createNamedExportFrom = _createNamedExportFrom._createNamedExportFrom;
exports._createStarExport = _createStarExport._createStarExport;
exports._interopDefault = _interopDefault$1._interopDefault;
exports._interopNamespace = _interopNamespace$1._interopNamespace;
exports._interopNamespaceDefaultOnly = _interopNamespaceDefaultOnly$1._interopNamespaceDefaultOnly;
exports._interopRequireDefault = _interopRequireDefault._interopRequireDefault;
exports._interopRequireWildcard = _interopRequireWildcard._interopRequireWildcard;
exports._nullishCoalesce = _nullishCoalesce._nullishCoalesce;
exports._optionalChain = _optionalChain._optionalChain;
exports._optionalChainDelete = _optionalChainDelete._optionalChainDelete;


},{"./_asyncNullishCoalesce.js":111,"./_asyncOptionalChain.js":112,"./_asyncOptionalChainDelete.js":113,"./_createNamedExportFrom.js":114,"./_createStarExport.js":115,"./_interopDefault.js":116,"./_interopNamespace.js":117,"./_interopNamespaceDefaultOnly.js":118,"./_interopRequireDefault.js":119,"./_interopRequireWildcard.js":120,"./_nullishCoalesce.js":121,"./_optionalChain.js":122,"./_optionalChainDelete.js":123}],125:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const envelope = require('./envelope.js');
const time = require('./time.js');

/**
 * Creates client report envelope
 * @param discarded_events An array of discard events
 * @param dsn A DSN that can be set on the header. Optional.
 */
function createClientReportEnvelope(
  discarded_events,
  dsn,
  timestamp,
) {
  const clientReportItem = [
    { type: 'client_report' },
    {
      timestamp: timestamp || time.dateTimestampInSeconds(),
      discarded_events,
    },
  ];
  return envelope.createEnvelope(dsn ? { dsn } : {}, [clientReportItem]);
}

exports.createClientReportEnvelope = createClientReportEnvelope;


},{"./envelope.js":128,"./time.js":148}],126:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const error = require('./error.js');

/** Regular expression used to parse a Dsn. */
const DSN_REGEX = /^(?:(\w+):)\/\/(?:(\w+)(?::(\w+)?)?@)([\w.-]+)(?::(\d+))?\/(.+)/;

function isValidProtocol(protocol) {
  return protocol === 'http' || protocol === 'https';
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
function dsnToString(dsn, withPassword = false) {
  const { host, path, pass, port, projectId, protocol, publicKey } = dsn;
  return (
    `${protocol}://${publicKey}${withPassword && pass ? `:${pass}` : ''}` +
    `@${host}${port ? `:${port}` : ''}/${path ? `${path}/` : path}${projectId}`
  );
}

/**
 * Parses a Dsn from a given string.
 *
 * @param str A Dsn as string
 * @returns Dsn as DsnComponents
 */
function dsnFromString(str) {
  const match = DSN_REGEX.exec(str);

  if (!match) {
    throw new error.SentryError(`Invalid Sentry Dsn: ${str}`);
  }

  const [protocol, publicKey, pass = '', host, port = '', lastPath] = match.slice(1);
  let path = '';
  let projectId = lastPath;

  const split = projectId.split('/');
  if (split.length > 1) {
    path = split.slice(0, -1).join('/');
    projectId = split.pop() ;
  }

  if (projectId) {
    const projectMatch = projectId.match(/^\d+/);
    if (projectMatch) {
      projectId = projectMatch[0];
    }
  }

  return dsnFromComponents({ host, pass, path, projectId, port, protocol: protocol , publicKey });
}

function dsnFromComponents(components) {
  return {
    protocol: components.protocol,
    publicKey: components.publicKey || '',
    pass: components.pass || '',
    host: components.host,
    port: components.port || '',
    path: components.path || '',
    projectId: components.projectId,
  };
}

function validateDsn(dsn) {
  if (!(typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__)) {
    return;
  }

  const { port, projectId, protocol } = dsn;

  const requiredComponents = ['protocol', 'publicKey', 'host', 'projectId'];
  requiredComponents.forEach(component => {
    if (!dsn[component]) {
      throw new error.SentryError(`Invalid Sentry Dsn: ${component} missing`);
    }
  });

  if (!projectId.match(/^\d+$/)) {
    throw new error.SentryError(`Invalid Sentry Dsn: Invalid projectId ${projectId}`);
  }

  if (!isValidProtocol(protocol)) {
    throw new error.SentryError(`Invalid Sentry Dsn: Invalid protocol ${protocol}`);
  }

  if (port && isNaN(parseInt(port, 10))) {
    throw new error.SentryError(`Invalid Sentry Dsn: Invalid port ${port}`);
  }

  return true;
}

/** The Sentry Dsn, identifying a Sentry instance and project. */
function makeDsn(from) {
  const components = typeof from === 'string' ? dsnFromString(from) : dsnFromComponents(from);
  validateDsn(components);
  return components;
}

exports.dsnFromString = dsnFromString;
exports.dsnToString = dsnToString;
exports.makeDsn = makeDsn;


},{"./error.js":129}],127:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/*
 * This module exists for optimizations in the build process through rollup and terser.  We define some global
 * constants, which can be overridden during build. By guarding certain pieces of code with functions that return these
 * constants, we can control whether or not they appear in the final bundle. (Any code guarded by a false condition will
 * never run, and will hence be dropped during treeshaking.) The two primary uses for this are stripping out calls to
 * `logger` and preventing node-related code from appearing in browser bundles.
 *
 * Attention:
 * This file should not be used to define constants/flags that are intended to be used for tree-shaking conducted by
 * users. These fags should live in their respective packages, as we identified user tooling (specifically webpack)
 * having issues tree-shaking these constants across package boundaries.
 * An example for this is the __SENTRY_DEBUG__ constant. It is declared in each package individually because we want
 * users to be able to shake away expressions that it guards.
 */

/**
 * Figures out if we're building a browser bundle.
 *
 * @returns true if this is a browser bundle build.
 */
function isBrowserBundle() {
  return typeof __SENTRY_BROWSER_BUNDLE__ !== 'undefined' && !!__SENTRY_BROWSER_BUNDLE__;
}

exports.isBrowserBundle = isBrowserBundle;


},{}],128:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const dsn = require('./dsn.js');
const normalize = require('./normalize.js');
const object = require('./object.js');

/**
 * Creates an envelope.
 * Make sure to always explicitly provide the generic to this function
 * so that the envelope types resolve correctly.
 */
function createEnvelope(headers, items = []) {
  return [headers, items] ;
}

/**
 * Add an item to an envelope.
 * Make sure to always explicitly provide the generic to this function
 * so that the envelope types resolve correctly.
 */
function addItemToEnvelope(envelope, newItem) {
  const [headers, items] = envelope;
  return [headers, [...items, newItem]] ;
}

/**
 * Convenience function to loop through the items and item types of an envelope.
 * (This function was mostly created because working with envelope types is painful at the moment)
 */
function forEachEnvelopeItem(
  envelope,
  callback,
) {
  const envelopeItems = envelope[1];
  envelopeItems.forEach((envelopeItem) => {
    const envelopeItemType = envelopeItem[0].type;
    callback(envelopeItem, envelopeItemType);
  });
}

function encodeUTF8(input, textEncoder) {
  const utf8 = textEncoder || new TextEncoder();
  return utf8.encode(input);
}

/**
 * Serializes an envelope.
 */
function serializeEnvelope(envelope, textEncoder) {
  const [envHeaders, items] = envelope;

  // Initially we construct our envelope as a string and only convert to binary chunks if we encounter binary data
  let parts = JSON.stringify(envHeaders);

  function append(next) {
    if (typeof parts === 'string') {
      parts = typeof next === 'string' ? parts + next : [encodeUTF8(parts, textEncoder), next];
    } else {
      parts.push(typeof next === 'string' ? encodeUTF8(next, textEncoder) : next);
    }
  }

  for (const item of items) {
    const [itemHeaders, payload] = item;

    append(`\n${JSON.stringify(itemHeaders)}\n`);

    if (typeof payload === 'string' || payload instanceof Uint8Array) {
      append(payload);
    } else {
      let stringifiedPayload;
      try {
        stringifiedPayload = JSON.stringify(payload);
      } catch (e) {
        // In case, despite all our efforts to keep `payload` circular-dependency-free, `JSON.strinify()` still
        // fails, we try again after normalizing it again with infinite normalization depth. This of course has a
        // performance impact but in this case a performance hit is better than throwing.
        stringifiedPayload = JSON.stringify(normalize.normalize(payload));
      }
      append(stringifiedPayload);
    }
  }

  return typeof parts === 'string' ? parts : concatBuffers(parts);
}

function concatBuffers(buffers) {
  const totalLength = buffers.reduce((acc, buf) => acc + buf.length, 0);

  const merged = new Uint8Array(totalLength);
  let offset = 0;
  for (const buffer of buffers) {
    merged.set(buffer, offset);
    offset += buffer.length;
  }

  return merged;
}

/**
 * Parses an envelope
 */
function parseEnvelope(
  env,
  textEncoder,
  textDecoder,
) {
  let buffer = typeof env === 'string' ? textEncoder.encode(env) : env;

  function readBinary(length) {
    const bin = buffer.subarray(0, length);
    // Replace the buffer with the remaining data excluding trailing newline
    buffer = buffer.subarray(length + 1);
    return bin;
  }

  function readJson() {
    let i = buffer.indexOf(0xa);
    // If we couldn't find a newline, we must have found the end of the buffer
    if (i < 0) {
      i = buffer.length;
    }

    return JSON.parse(textDecoder.decode(readBinary(i))) ;
  }

  const envelopeHeader = readJson();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const items = [];

  while (buffer.length) {
    const itemHeader = readJson();
    const binaryLength = typeof itemHeader.length === 'number' ? itemHeader.length : undefined;

    items.push([itemHeader, binaryLength ? readBinary(binaryLength) : readJson()]);
  }

  return [envelopeHeader, items];
}

/**
 * Creates attachment envelope items
 */
function createAttachmentEnvelopeItem(
  attachment,
  textEncoder,
) {
  const buffer = typeof attachment.data === 'string' ? encodeUTF8(attachment.data, textEncoder) : attachment.data;

  return [
    object.dropUndefinedKeys({
      type: 'attachment',
      length: buffer.length,
      filename: attachment.filename,
      content_type: attachment.contentType,
      attachment_type: attachment.attachmentType,
    }),
    buffer,
  ];
}

const ITEM_TYPE_TO_DATA_CATEGORY_MAP = {
  session: 'session',
  sessions: 'session',
  attachment: 'attachment',
  transaction: 'transaction',
  event: 'error',
  client_report: 'internal',
  user_report: 'default',
  profile: 'profile',
};

/**
 * Maps the type of an envelope item to a data category.
 */
function envelopeItemTypeToDataCategory(type) {
  return ITEM_TYPE_TO_DATA_CATEGORY_MAP[type];
}

/** Extracts the minimal SDK info from from the metadata or an events */
function getSdkMetadataForEnvelopeHeader(metadataOrEvent) {
  if (!metadataOrEvent || !metadataOrEvent.sdk) {
    return;
  }
  const { name, version } = metadataOrEvent.sdk;
  return { name, version };
}

/**
 * Creates event envelope headers, based on event, sdk info and tunnel
 * Note: This function was extracted from the core package to make it available in Replay
 */
function createEventEnvelopeHeaders(
  event,
  sdkInfo,
  tunnel,
  dsn$1,
) {
  const dynamicSamplingContext = event.sdkProcessingMetadata && event.sdkProcessingMetadata.dynamicSamplingContext;

  return {
    event_id: event.event_id ,
    sent_at: new Date().toISOString(),
    ...(sdkInfo && { sdk: sdkInfo }),
    ...(!!tunnel && { dsn: dsn.dsnToString(dsn$1) }),
    ...(event.type === 'transaction' &&
      dynamicSamplingContext && {
        trace: object.dropUndefinedKeys({ ...dynamicSamplingContext }),
      }),
  };
}

exports.addItemToEnvelope = addItemToEnvelope;
exports.createAttachmentEnvelopeItem = createAttachmentEnvelopeItem;
exports.createEnvelope = createEnvelope;
exports.createEventEnvelopeHeaders = createEventEnvelopeHeaders;
exports.envelopeItemTypeToDataCategory = envelopeItemTypeToDataCategory;
exports.forEachEnvelopeItem = forEachEnvelopeItem;
exports.getSdkMetadataForEnvelopeHeader = getSdkMetadataForEnvelopeHeader;
exports.parseEnvelope = parseEnvelope;
exports.serializeEnvelope = serializeEnvelope;


},{"./dsn.js":126,"./normalize.js":137,"./object.js":138}],129:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/** An error emitted by Sentry SDKs and related utilities. */
class SentryError extends Error {
  /** Display name of this error instance. */

   constructor( message, logLevel = 'warn') {
    super(message);this.message = message;;

    this.name = new.target.prototype.constructor.name;
    // This sets the prototype to be `Error`, not `SentryError`. It's unclear why we do this, but commenting this line
    // out causes various (seemingly totally unrelated) playwright tests consistently time out. FYI, this makes
    // instances of `SentryError` fail `obj instanceof SentryError` checks.
    Object.setPrototypeOf(this, new.target.prototype);
    this.logLevel = logLevel;
  }
}

exports.SentryError = SentryError;


},{}],130:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const browser = require('./browser.js');
const dsn = require('./dsn.js');
const error = require('./error.js');
const worldwide = require('./worldwide.js');
const instrument = require('./instrument.js');
const is = require('./is.js');
const logger = require('./logger.js');
const memo = require('./memo.js');
const misc = require('./misc.js');
const node = require('./node.js');
const normalize = require('./normalize.js');
const object = require('./object.js');
const path = require('./path.js');
const promisebuffer = require('./promisebuffer.js');
const requestdata = require('./requestdata.js');
const severity = require('./severity.js');
const stacktrace = require('./stacktrace.js');
const string = require('./string.js');
const supports = require('./supports.js');
const syncpromise = require('./syncpromise.js');
const time = require('./time.js');
const tracing = require('./tracing.js');
const env = require('./env.js');
const envelope = require('./envelope.js');
const clientreport = require('./clientreport.js');
const ratelimit = require('./ratelimit.js');
const baggage = require('./baggage.js');
const url = require('./url.js');



exports.getDomElement = browser.getDomElement;
exports.getLocationHref = browser.getLocationHref;
exports.htmlTreeAsString = browser.htmlTreeAsString;
exports.dsnFromString = dsn.dsnFromString;
exports.dsnToString = dsn.dsnToString;
exports.makeDsn = dsn.makeDsn;
exports.SentryError = error.SentryError;
exports.GLOBAL_OBJ = worldwide.GLOBAL_OBJ;
exports.getGlobalObject = worldwide.getGlobalObject;
exports.getGlobalSingleton = worldwide.getGlobalSingleton;
exports.addInstrumentationHandler = instrument.addInstrumentationHandler;
exports.isDOMError = is.isDOMError;
exports.isDOMException = is.isDOMException;
exports.isElement = is.isElement;
exports.isError = is.isError;
exports.isErrorEvent = is.isErrorEvent;
exports.isEvent = is.isEvent;
exports.isInstanceOf = is.isInstanceOf;
exports.isNaN = is.isNaN;
exports.isPlainObject = is.isPlainObject;
exports.isPrimitive = is.isPrimitive;
exports.isRegExp = is.isRegExp;
exports.isString = is.isString;
exports.isSyntheticEvent = is.isSyntheticEvent;
exports.isThenable = is.isThenable;
exports.CONSOLE_LEVELS = logger.CONSOLE_LEVELS;
exports.consoleSandbox = logger.consoleSandbox;
Object.defineProperty(exports, 'logger', {
	enumerable: true,
	get: () => logger.logger
});
exports.memoBuilder = memo.memoBuilder;
exports.addContextToFrame = misc.addContextToFrame;
exports.addExceptionMechanism = misc.addExceptionMechanism;
exports.addExceptionTypeValue = misc.addExceptionTypeValue;
exports.arrayify = misc.arrayify;
exports.checkOrSetAlreadyCaught = misc.checkOrSetAlreadyCaught;
exports.getEventDescription = misc.getEventDescription;
exports.parseSemver = misc.parseSemver;
exports.uuid4 = misc.uuid4;
exports.dynamicRequire = node.dynamicRequire;
exports.isNodeEnv = node.isNodeEnv;
exports.loadModule = node.loadModule;
exports.normalize = normalize.normalize;
exports.normalizeToSize = normalize.normalizeToSize;
exports.walk = normalize.walk;
exports.addNonEnumerableProperty = object.addNonEnumerableProperty;
exports.convertToPlainObject = object.convertToPlainObject;
exports.dropUndefinedKeys = object.dropUndefinedKeys;
exports.extractExceptionKeysForMessage = object.extractExceptionKeysForMessage;
exports.fill = object.fill;
exports.getOriginalFunction = object.getOriginalFunction;
exports.markFunctionWrapped = object.markFunctionWrapped;
exports.objectify = object.objectify;
exports.urlEncode = object.urlEncode;
exports.basename = path.basename;
exports.dirname = path.dirname;
exports.isAbsolute = path.isAbsolute;
exports.join = path.join;
exports.normalizePath = path.normalizePath;
exports.relative = path.relative;
exports.resolve = path.resolve;
exports.makePromiseBuffer = promisebuffer.makePromiseBuffer;
exports.addRequestDataToEvent = requestdata.addRequestDataToEvent;
exports.addRequestDataToTransaction = requestdata.addRequestDataToTransaction;
exports.extractPathForTransaction = requestdata.extractPathForTransaction;
exports.extractRequestData = requestdata.extractRequestData;
exports.severityFromString = severity.severityFromString;
exports.severityLevelFromString = severity.severityLevelFromString;
exports.validSeverityLevels = severity.validSeverityLevels;
exports.createStackParser = stacktrace.createStackParser;
exports.getFunctionName = stacktrace.getFunctionName;
exports.nodeStackLineParser = stacktrace.nodeStackLineParser;
exports.stackParserFromStackParserOptions = stacktrace.stackParserFromStackParserOptions;
exports.stripSentryFramesAndReverse = stacktrace.stripSentryFramesAndReverse;
exports.escapeStringForRegex = string.escapeStringForRegex;
exports.isMatchingPattern = string.isMatchingPattern;
exports.safeJoin = string.safeJoin;
exports.snipLine = string.snipLine;
exports.stringMatchesSomePattern = string.stringMatchesSomePattern;
exports.truncate = string.truncate;
exports.isNativeFetch = supports.isNativeFetch;
exports.supportsDOMError = supports.supportsDOMError;
exports.supportsDOMException = supports.supportsDOMException;
exports.supportsErrorEvent = supports.supportsErrorEvent;
exports.supportsFetch = supports.supportsFetch;
exports.supportsHistory = supports.supportsHistory;
exports.supportsNativeFetch = supports.supportsNativeFetch;
exports.supportsReferrerPolicy = supports.supportsReferrerPolicy;
exports.supportsReportingObserver = supports.supportsReportingObserver;
exports.SyncPromise = syncpromise.SyncPromise;
exports.rejectedSyncPromise = syncpromise.rejectedSyncPromise;
exports.resolvedSyncPromise = syncpromise.resolvedSyncPromise;
Object.defineProperty(exports, '_browserPerformanceTimeOriginMode', {
	enumerable: true,
	get: () => time._browserPerformanceTimeOriginMode
});
exports.browserPerformanceTimeOrigin = time.browserPerformanceTimeOrigin;
exports.dateTimestampInSeconds = time.dateTimestampInSeconds;
exports.timestampInSeconds = time.timestampInSeconds;
exports.timestampWithMs = time.timestampWithMs;
exports.usingPerformanceAPI = time.usingPerformanceAPI;
exports.TRACEPARENT_REGEXP = tracing.TRACEPARENT_REGEXP;
exports.extractTraceparentData = tracing.extractTraceparentData;
exports.isBrowserBundle = env.isBrowserBundle;
exports.addItemToEnvelope = envelope.addItemToEnvelope;
exports.createAttachmentEnvelopeItem = envelope.createAttachmentEnvelopeItem;
exports.createEnvelope = envelope.createEnvelope;
exports.createEventEnvelopeHeaders = envelope.createEventEnvelopeHeaders;
exports.envelopeItemTypeToDataCategory = envelope.envelopeItemTypeToDataCategory;
exports.forEachEnvelopeItem = envelope.forEachEnvelopeItem;
exports.getSdkMetadataForEnvelopeHeader = envelope.getSdkMetadataForEnvelopeHeader;
exports.parseEnvelope = envelope.parseEnvelope;
exports.serializeEnvelope = envelope.serializeEnvelope;
exports.createClientReportEnvelope = clientreport.createClientReportEnvelope;
exports.DEFAULT_RETRY_AFTER = ratelimit.DEFAULT_RETRY_AFTER;
exports.disabledUntil = ratelimit.disabledUntil;
exports.isRateLimited = ratelimit.isRateLimited;
exports.parseRetryAfterHeader = ratelimit.parseRetryAfterHeader;
exports.updateRateLimits = ratelimit.updateRateLimits;
exports.BAGGAGE_HEADER_NAME = baggage.BAGGAGE_HEADER_NAME;
exports.MAX_BAGGAGE_STRING_LENGTH = baggage.MAX_BAGGAGE_STRING_LENGTH;
exports.SENTRY_BAGGAGE_KEY_PREFIX = baggage.SENTRY_BAGGAGE_KEY_PREFIX;
exports.SENTRY_BAGGAGE_KEY_PREFIX_REGEX = baggage.SENTRY_BAGGAGE_KEY_PREFIX_REGEX;
exports.baggageHeaderToDynamicSamplingContext = baggage.baggageHeaderToDynamicSamplingContext;
exports.dynamicSamplingContextToSentryBaggageHeader = baggage.dynamicSamplingContextToSentryBaggageHeader;
exports.getNumberOfUrlSegments = url.getNumberOfUrlSegments;
exports.parseUrl = url.parseUrl;
exports.stripUrlQueryAndFragment = url.stripUrlQueryAndFragment;


},{"./baggage.js":109,"./browser.js":110,"./clientreport.js":125,"./dsn.js":126,"./env.js":127,"./envelope.js":128,"./error.js":129,"./instrument.js":131,"./is.js":132,"./logger.js":133,"./memo.js":134,"./misc.js":135,"./node.js":136,"./normalize.js":137,"./object.js":138,"./path.js":139,"./promisebuffer.js":140,"./ratelimit.js":141,"./requestdata.js":142,"./severity.js":143,"./stacktrace.js":144,"./string.js":145,"./supports.js":146,"./syncpromise.js":147,"./time.js":148,"./tracing.js":149,"./url.js":150,"./worldwide.js":151}],131:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');
const logger = require('./logger.js');
const object = require('./object.js');
const stacktrace = require('./stacktrace.js');
const supports = require('./supports.js');
const worldwide = require('./worldwide.js');

// eslint-disable-next-line deprecation/deprecation
const WINDOW = worldwide.getGlobalObject();

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

const handlers = {};
const instrumented = {};

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
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) && logger.logger.warn('unknown instrumentation type:', type);
      return;
  }
}

/**
 * Add handler that will be called when given type of instrumentation triggers.
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addInstrumentationHandler(type, callback) {
  handlers[type] = handlers[type] || [];
  (handlers[type] ).push(callback);
  instrument(type);
}

/** JSDoc */
function triggerHandlers(type, data) {
  if (!type || !handlers[type]) {
    return;
  }

  for (const handler of handlers[type] || []) {
    try {
      handler(data);
    } catch (e) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
        logger.logger.error(
          `Error while triggering instrumentation handler.\nType: ${type}\nName: ${stacktrace.getFunctionName(handler)}\nError:`,
          e,
        );
    }
  }
}

/** JSDoc */
function instrumentConsole() {
  if (!('console' in WINDOW)) {
    return;
  }

  logger.CONSOLE_LEVELS.forEach(function (level) {
    if (!(level in WINDOW.console)) {
      return;
    }

    object.fill(WINDOW.console, level, function (originalConsoleMethod) {
      return function (...args) {
        triggerHandlers('console', { args, level });

        // this fails for some browsers. :(
        if (originalConsoleMethod) {
          originalConsoleMethod.apply(WINDOW.console, args);
        }
      };
    });
  });
}

/** JSDoc */
function instrumentFetch() {
  if (!supports.supportsNativeFetch()) {
    return;
  }

  object.fill(WINDOW, 'fetch', function (originalFetch) {
    return function (...args) {
      const handlerData = {
        args,
        fetchData: {
          method: getFetchMethod(args),
          url: getFetchUrl(args),
        },
        startTimestamp: Date.now(),
      };

      triggerHandlers('fetch', {
        ...handlerData,
      });

      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      return originalFetch.apply(WINDOW, args).then(
        (response) => {
          triggerHandlers('fetch', {
            ...handlerData,
            endTimestamp: Date.now(),
            response,
          });
          return response;
        },
        (error) => {
          triggerHandlers('fetch', {
            ...handlerData,
            endTimestamp: Date.now(),
            error,
          });
          // NOTE: If you are a Sentry user, and you are seeing this stack frame,
          //       it means the sentry.javascript SDK caught an error invoking your application code.
          //       This is expected behavior and NOT indicative of a bug with sentry.javascript.
          throw error;
        },
      );
    };
  });
}

/* eslint-disable @typescript-eslint/no-unsafe-member-access */
/** Extract `method` from fetch call arguments */
function getFetchMethod(fetchArgs = []) {
  if ('Request' in WINDOW && is.isInstanceOf(fetchArgs[0], Request) && fetchArgs[0].method) {
    return String(fetchArgs[0].method).toUpperCase();
  }
  if (fetchArgs[1] && fetchArgs[1].method) {
    return String(fetchArgs[1].method).toUpperCase();
  }
  return 'GET';
}

/** Extract `url` from fetch call arguments */
function getFetchUrl(fetchArgs = []) {
  if (typeof fetchArgs[0] === 'string') {
    return fetchArgs[0];
  }
  if ('Request' in WINDOW && is.isInstanceOf(fetchArgs[0], Request)) {
    return fetchArgs[0].url;
  }
  return String(fetchArgs[0]);
}
/* eslint-enable @typescript-eslint/no-unsafe-member-access */

/** JSDoc */
function instrumentXHR() {
  if (!('XMLHttpRequest' in WINDOW)) {
    return;
  }

  const xhrproto = XMLHttpRequest.prototype;

  object.fill(xhrproto, 'open', function (originalOpen) {
    return function ( ...args) {
      // eslint-disable-next-line @typescript-eslint/no-this-alias
      const xhr = this;
      const url = args[1];
      const xhrInfo = (xhr.__sentry_xhr__ = {
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        method: is.isString(args[0]) ? args[0].toUpperCase() : args[0],
        url: args[1],
      });

      // if Sentry key appears in URL, don't capture it as a request
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      if (is.isString(url) && xhrInfo.method === 'POST' && url.match(/sentry_key/)) {
        xhr.__sentry_own_request__ = true;
      }

      const onreadystatechangeHandler = function () {
        if (xhr.readyState === 4) {
          try {
            // touching statusCode in some platforms throws
            // an exception
            xhrInfo.status_code = xhr.status;
          } catch (e) {
            /* do nothing */
          }

          triggerHandlers('xhr', {
            args,
            endTimestamp: Date.now(),
            startTimestamp: Date.now(),
            xhr,
          });
        }
      };

      if ('onreadystatechange' in xhr && typeof xhr.onreadystatechange === 'function') {
        object.fill(xhr, 'onreadystatechange', function (original) {
          return function (...readyStateArgs) {
            onreadystatechangeHandler();
            return original.apply(xhr, readyStateArgs);
          };
        });
      } else {
        xhr.addEventListener('readystatechange', onreadystatechangeHandler);
      }

      return originalOpen.apply(xhr, args);
    };
  });

  object.fill(xhrproto, 'send', function (originalSend) {
    return function ( ...args) {
      if (this.__sentry_xhr__ && args[0] !== undefined) {
        this.__sentry_xhr__.body = args[0];
      }

      triggerHandlers('xhr', {
        args,
        startTimestamp: Date.now(),
        xhr: this,
      });

      return originalSend.apply(this, args);
    };
  });
}

let lastHref;

/** JSDoc */
function instrumentHistory() {
  if (!supports.supportsHistory()) {
    return;
  }

  const oldOnPopState = WINDOW.onpopstate;
  WINDOW.onpopstate = function ( ...args) {
    const to = WINDOW.location.href;
    // keep track of the current URL state, as we always receive only the updated state
    const from = lastHref;
    lastHref = to;
    triggerHandlers('history', {
      from,
      to,
    });
    if (oldOnPopState) {
      // Apparently this can throw in Firefox when incorrectly implemented plugin is installed.
      // https://github.com/getsentry/sentry-javascript/issues/3344
      // https://github.com/bugsnag/bugsnag-js/issues/469
      try {
        return oldOnPopState.apply(this, args);
      } catch (_oO) {
        // no-empty
      }
    }
  };

  /** @hidden */
  function historyReplacementFunction(originalHistoryFunction) {
    return function ( ...args) {
      const url = args.length > 2 ? args[2] : undefined;
      if (url) {
        // coerce to string (this is what pushState does)
        const from = lastHref;
        const to = String(url);
        // keep track of the current URL state, as we always receive only the updated state
        lastHref = to;
        triggerHandlers('history', {
          from,
          to,
        });
      }
      return originalHistoryFunction.apply(this, args);
    };
  }

  object.fill(WINDOW.history, 'pushState', historyReplacementFunction);
  object.fill(WINDOW.history, 'replaceState', historyReplacementFunction);
}

const debounceDuration = 1000;
let debounceTimerID;
let lastCapturedEvent;

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
  } catch (e) {
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
    const target = event.target ;

    if (!target || !target.tagName) {
      return true;
    }

    // Only consider keypress events on actual input elements. This will disregard keypresses targeting body
    // e.g.tabbing through elements, hotkeys, etc.
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      return false;
    }
  } catch (e) {
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
function makeDOMEventHandler(handler, globalListener = false) {
  return (event) => {
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

    const name = event.type === 'keypress' ? 'input' : event.type;

    // If there is no debounce timer, it means that we can safely capture the new event and store it for future comparisons.
    if (debounceTimerID === undefined) {
      handler({
        event: event,
        name,
        global: globalListener,
      });
      lastCapturedEvent = event;
    }
    // If there is a debounce awaiting, see if the new event is different enough to treat it as a unique one.
    // If that's the case, emit the previous event and store locally the newly-captured DOM event.
    else if (shouldShortcircuitPreviousDebounce(lastCapturedEvent, event)) {
      handler({
        event: event,
        name,
        global: globalListener,
      });
      lastCapturedEvent = event;
    }

    // Start a new debounce timer that will prevent us from capturing multiple events that should be grouped together.
    clearTimeout(debounceTimerID);
    debounceTimerID = WINDOW.setTimeout(() => {
      debounceTimerID = undefined;
    }, debounceDuration);
  };
}

/** JSDoc */
function instrumentDOM() {
  if (!('document' in WINDOW)) {
    return;
  }

  // Make it so that any click or keypress that is unhandled / bubbled up all the way to the document triggers our dom
  // handlers. (Normally we have only one, which captures a breadcrumb for each click or keypress.) Do this before
  // we instrument `addEventListener` so that we don't end up attaching this handler twice.
  const triggerDOMHandler = triggerHandlers.bind(null, 'dom');
  const globalDOMEventHandler = makeDOMEventHandler(triggerDOMHandler, true);
  WINDOW.document.addEventListener('click', globalDOMEventHandler, false);
  WINDOW.document.addEventListener('keypress', globalDOMEventHandler, false);

  // After hooking into click and keypress events bubbled up to `document`, we also hook into user-handled
  // clicks & keypresses, by adding an event listener of our own to any element to which they add a listener. That
  // way, whenever one of their handlers is triggered, ours will be, too. (This is needed because their handler
  // could potentially prevent the event from bubbling up to our global listeners. This way, our handler are still
  // guaranteed to fire at least once.)
  ['EventTarget', 'Node'].forEach((target) => {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    const proto = (WINDOW )[target] && (WINDOW )[target].prototype;
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access, no-prototype-builtins
    if (!proto || !proto.hasOwnProperty || !proto.hasOwnProperty('addEventListener')) {
      return;
    }

    object.fill(proto, 'addEventListener', function (originalAddEventListener) {
      return function (

        type,
        listener,
        options,
      ) {
        if (type === 'click' || type == 'keypress') {
          try {
            const el = this ;
            const handlers = (el.__sentry_instrumentation_handlers__ = el.__sentry_instrumentation_handlers__ || {});
            const handlerForType = (handlers[type] = handlers[type] || { refCount: 0 });

            if (!handlerForType.handler) {
              const handler = makeDOMEventHandler(triggerDOMHandler);
              handlerForType.handler = handler;
              originalAddEventListener.call(this, type, handler, options);
            }

            handlerForType.refCount++;
          } catch (e) {
            // Accessing dom properties is always fragile.
            // Also allows us to skip `addEventListenrs` calls with no proper `this` context.
          }
        }

        return originalAddEventListener.call(this, type, listener, options);
      };
    });

    object.fill(
      proto,
      'removeEventListener',
      function (originalRemoveEventListener) {
        return function (

          type,
          listener,
          options,
        ) {
          if (type === 'click' || type == 'keypress') {
            try {
              const el = this ;
              const handlers = el.__sentry_instrumentation_handlers__ || {};
              const handlerForType = handlers[type];

              if (handlerForType) {
                handlerForType.refCount--;
                // If there are no longer any custom handlers of the current type on this element, we can remove ours, too.
                if (handlerForType.refCount <= 0) {
                  originalRemoveEventListener.call(this, type, handlerForType.handler, options);
                  handlerForType.handler = undefined;
                  delete handlers[type]; // eslint-disable-line @typescript-eslint/no-dynamic-delete
                }

                // If there are no longer any custom handlers of any type on this element, cleanup everything.
                if (Object.keys(handlers).length === 0) {
                  delete el.__sentry_instrumentation_handlers__;
                }
              }
            } catch (e) {
              // Accessing dom properties is always fragile.
              // Also allows us to skip `addEventListenrs` calls with no proper `this` context.
            }
          }

          return originalRemoveEventListener.call(this, type, listener, options);
        };
      },
    );
  });
}

let _oldOnErrorHandler = null;
/** JSDoc */
function instrumentError() {
  _oldOnErrorHandler = WINDOW.onerror;

  WINDOW.onerror = function (msg, url, line, column, error) {
    triggerHandlers('error', {
      column,
      error,
      line,
      msg,
      url,
    });

    if (_oldOnErrorHandler) {
      // eslint-disable-next-line prefer-rest-params
      return _oldOnErrorHandler.apply(this, arguments);
    }

    return false;
  };
}

let _oldOnUnhandledRejectionHandler = null;
/** JSDoc */
function instrumentUnhandledRejection() {
  _oldOnUnhandledRejectionHandler = WINDOW.onunhandledrejection;

  WINDOW.onunhandledrejection = function (e) {
    triggerHandlers('unhandledrejection', e);

    if (_oldOnUnhandledRejectionHandler) {
      // eslint-disable-next-line prefer-rest-params
      return _oldOnUnhandledRejectionHandler.apply(this, arguments);
    }

    return true;
  };
}

exports.addInstrumentationHandler = addInstrumentationHandler;


},{"./is.js":132,"./logger.js":133,"./object.js":138,"./stacktrace.js":144,"./supports.js":146,"./worldwide.js":151}],132:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// eslint-disable-next-line @typescript-eslint/unbound-method
const objectToString = Object.prototype.toString;

/**
 * Checks whether given value's type is one of a few Error or Error-like
 * {@link isError}.
 *
 * @param wat A value to be checked.
 * @returns A boolean representing the result.
 */
function isError(wat) {
  switch (objectToString.call(wat)) {
    case '[object Error]':
    case '[object Exception]':
    case '[object DOMException]':
      return true;
    default:
      return isInstanceOf(wat, Error);
  }
}
/**
 * Checks whether given value is an instance of the given built-in class.
 *
 * @param wat The value to be checked
 * @param className
 * @returns A boolean representing the result.
 */
function isBuiltin(wat, className) {
  return objectToString.call(wat) === `[object ${className}]`;
}

/**
 * Checks whether given value's type is ErrorEvent
 * {@link isErrorEvent}.
 *
 * @param wat A value to be checked.
 * @returns A boolean representing the result.
 */
function isErrorEvent(wat) {
  return isBuiltin(wat, 'ErrorEvent');
}

/**
 * Checks whether given value's type is DOMError
 * {@link isDOMError}.
 *
 * @param wat A value to be checked.
 * @returns A boolean representing the result.
 */
function isDOMError(wat) {
  return isBuiltin(wat, 'DOMError');
}

/**
 * Checks whether given value's type is DOMException
 * {@link isDOMException}.
 *
 * @param wat A value to be checked.
 * @returns A boolean representing the result.
 */
function isDOMException(wat) {
  return isBuiltin(wat, 'DOMException');
}

/**
 * Checks whether given value's type is a string
 * {@link isString}.
 *
 * @param wat A value to be checked.
 * @returns A boolean representing the result.
 */
function isString(wat) {
  return isBuiltin(wat, 'String');
}

/**
 * Checks whether given value is a primitive (undefined, null, number, boolean, string, bigint, symbol)
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
  return isBuiltin(wat, 'Object');
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
  return isBuiltin(wat, 'RegExp');
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
 * Checks whether given value is NaN
 * {@link isNaN}.
 *
 * @param wat A value to be checked.
 * @returns A boolean representing the result.
 */
function isNaN(wat) {
  return typeof wat === 'number' && wat !== wat;
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
  } catch (_e) {
    return false;
  }
}

exports.isDOMError = isDOMError;
exports.isDOMException = isDOMException;
exports.isElement = isElement;
exports.isError = isError;
exports.isErrorEvent = isErrorEvent;
exports.isEvent = isEvent;
exports.isInstanceOf = isInstanceOf;
exports.isNaN = isNaN;
exports.isPlainObject = isPlainObject;
exports.isPrimitive = isPrimitive;
exports.isRegExp = isRegExp;
exports.isString = isString;
exports.isSyntheticEvent = isSyntheticEvent;
exports.isThenable = isThenable;


},{}],133:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const worldwide = require('./worldwide.js');

/** Prefix for logging strings */
const PREFIX = 'Sentry Logger ';

const CONSOLE_LEVELS = ['debug', 'info', 'warn', 'error', 'log', 'assert', 'trace'] ;

/**
 * Temporarily disable sentry console instrumentations.
 *
 * @param callback The function to run against the original `console` messages
 * @returns The results of the callback
 */
function consoleSandbox(callback) {
  if (!('console' in worldwide.GLOBAL_OBJ)) {
    return callback();
  }

  const originalConsole = worldwide.GLOBAL_OBJ.console ;
  const wrappedLevels = {};

  // Restore all wrapped console methods
  CONSOLE_LEVELS.forEach(level => {
    // TODO(v7): Remove this check as it's only needed for Node 6
    const originalWrappedFunc =
      originalConsole[level] && (originalConsole[level] ).__sentry_original__;
    if (level in originalConsole && originalWrappedFunc) {
      wrappedLevels[level] = originalConsole[level] ;
      originalConsole[level] = originalWrappedFunc ;
    }
  });

  try {
    return callback();
  } finally {
    // Revert restoration to wrapped state
    Object.keys(wrappedLevels).forEach(level => {
      originalConsole[level] = wrappedLevels[level ];
    });
  }
}

function makeLogger() {
  let enabled = false;
  const logger = {
    enable: () => {
      enabled = true;
    },
    disable: () => {
      enabled = false;
    },
  };

  if ((typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__)) {
    CONSOLE_LEVELS.forEach(name => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      logger[name] = (...args) => {
        if (enabled) {
          consoleSandbox(() => {
            worldwide.GLOBAL_OBJ.console[name](`${PREFIX}[${name}]:`, ...args);
          });
        }
      };
    });
  } else {
    CONSOLE_LEVELS.forEach(name => {
      logger[name] = () => undefined;
    });
  }

  return logger ;
}

// Ensure we only have a single logger instance, even if multiple versions of @sentry/utils are being used
exports.logger = void 0;
if ((typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__)) {
  exports.logger = worldwide.getGlobalSingleton('logger', makeLogger);
} else {
  exports.logger = makeLogger();
}

exports.CONSOLE_LEVELS = CONSOLE_LEVELS;
exports.consoleSandbox = consoleSandbox;


},{"./worldwide.js":151}],134:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/* eslint-disable @typescript-eslint/no-unsafe-member-access */
/* eslint-disable @typescript-eslint/no-explicit-any */

/**
 * Helper to decycle json objects
 */
function memoBuilder() {
  const hasWeakSet = typeof WeakSet === 'function';
  const inner = hasWeakSet ? new WeakSet() : [];
  function memoize(obj) {
    if (hasWeakSet) {
      if (inner.has(obj)) {
        return true;
      }
      inner.add(obj);
      return false;
    }
    // eslint-disable-next-line @typescript-eslint/prefer-for-of
    for (let i = 0; i < inner.length; i++) {
      const value = inner[i];
      if (value === obj) {
        return true;
      }
    }
    inner.push(obj);
    return false;
  }

  function unmemoize(obj) {
    if (hasWeakSet) {
      inner.delete(obj);
    } else {
      for (let i = 0; i < inner.length; i++) {
        if (inner[i] === obj) {
          inner.splice(i, 1);
          break;
        }
      }
    }
  }
  return [memoize, unmemoize];
}

exports.memoBuilder = memoBuilder;


},{}],135:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const object = require('./object.js');
const string = require('./string.js');
const worldwide = require('./worldwide.js');

/**
 * UUID4 generator
 *
 * @returns string Generated UUID4.
 */
function uuid4() {
  const gbl = worldwide.GLOBAL_OBJ ;
  const crypto = gbl.crypto || gbl.msCrypto;

  if (crypto && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, '');
  }

  const getRandomByte =
    crypto && crypto.getRandomValues ? () => crypto.getRandomValues(new Uint8Array(1))[0] : () => Math.random() * 16;

  // http://stackoverflow.com/questions/105034/how-to-create-a-guid-uuid-in-javascript/2117523#2117523
  // Concatenating the following numbers as strings results in '10000000100040008000100000000000'
  return (([1e7] ) + 1e3 + 4e3 + 8e3 + 1e11).replace(/[018]/g, c =>
    // eslint-disable-next-line no-bitwise
    ((c ) ^ ((getRandomByte() & 15) >> ((c ) / 4))).toString(16),
  );
}

function getFirstException(event) {
  return event.exception && event.exception.values ? event.exception.values[0] : undefined;
}

/**
 * Extracts either message or type+value from an event that can be used for user-facing logs
 * @returns event's description
 */
function getEventDescription(event) {
  const { message, event_id: eventId } = event;
  if (message) {
    return message;
  }

  const firstException = getFirstException(event);
  if (firstException) {
    if (firstException.type && firstException.value) {
      return `${firstException.type}: ${firstException.value}`;
    }
    return firstException.type || firstException.value || eventId || '<unknown>';
  }
  return eventId || '<unknown>';
}

/**
 * Adds exception values, type and value to an synthetic Exception.
 * @param event The event to modify.
 * @param value Value of the exception.
 * @param type Type of the exception.
 * @hidden
 */
function addExceptionTypeValue(event, value, type) {
  const exception = (event.exception = event.exception || {});
  const values = (exception.values = exception.values || []);
  const firstException = (values[0] = values[0] || {});
  if (!firstException.value) {
    firstException.value = value || '';
  }
  if (!firstException.type) {
    firstException.type = type || 'Error';
  }
}

/**
 * Adds exception mechanism data to a given event. Uses defaults if the second parameter is not passed.
 *
 * @param event The event to modify.
 * @param newMechanism Mechanism data to add to the event.
 * @hidden
 */
function addExceptionMechanism(event, newMechanism) {
  const firstException = getFirstException(event);
  if (!firstException) {
    return;
  }

  const defaultMechanism = { type: 'generic', handled: true };
  const currentMechanism = firstException.mechanism;
  firstException.mechanism = { ...defaultMechanism, ...currentMechanism, ...newMechanism };

  if (newMechanism && 'data' in newMechanism) {
    const mergedData = { ...(currentMechanism && currentMechanism.data), ...newMechanism.data };
    firstException.mechanism.data = mergedData;
  }
}

// https://semver.org/#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string
const SEMVER_REGEXP =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$/;

/**
 * Represents Semantic Versioning object
 */

/**
 * Parses input into a SemVer interface
 * @param input string representation of a semver version
 */
function parseSemver(input) {
  const match = input.match(SEMVER_REGEXP) || [];
  const major = parseInt(match[1], 10);
  const minor = parseInt(match[2], 10);
  const patch = parseInt(match[3], 10);
  return {
    buildmetadata: match[5],
    major: isNaN(major) ? undefined : major,
    minor: isNaN(minor) ? undefined : minor,
    patch: isNaN(patch) ? undefined : patch,
    prerelease: match[4],
  };
}

/**
 * This function adds context (pre/post/line) lines to the provided frame
 *
 * @param lines string[] containing all lines
 * @param frame StackFrame that will be mutated
 * @param linesOfContext number of context lines we want to add pre/post
 */
function addContextToFrame(lines, frame, linesOfContext = 5) {
  // When there is no line number in the frame, attaching context is nonsensical and will even break grouping
  if (frame.lineno === undefined) {
    return;
  }

  const maxLines = lines.length;
  const sourceLine = Math.max(Math.min(maxLines, frame.lineno - 1), 0);

  frame.pre_context = lines
    .slice(Math.max(0, sourceLine - linesOfContext), sourceLine)
    .map((line) => string.snipLine(line, 0));

  frame.context_line = string.snipLine(lines[Math.min(maxLines - 1, sourceLine)], frame.colno || 0);

  frame.post_context = lines
    .slice(Math.min(sourceLine + 1, maxLines), sourceLine + 1 + linesOfContext)
    .map((line) => string.snipLine(line, 0));
}

/**
 * Checks whether or not we've already captured the given exception (note: not an identical exception - the very object
 * in question), and marks it captured if not.
 *
 * This is useful because it's possible for an error to get captured by more than one mechanism. After we intercept and
 * record an error, we rethrow it (assuming we've intercepted it before it's reached the top-level global handlers), so
 * that we don't interfere with whatever effects the error might have had were the SDK not there. At that point, because
 * the error has been rethrown, it's possible for it to bubble up to some other code we've instrumented. If it's not
 * caught after that, it will bubble all the way up to the global handlers (which of course we also instrument). This
 * function helps us ensure that even if we encounter the same error more than once, we only record it the first time we
 * see it.
 *
 * Note: It will ignore primitives (always return `false` and not mark them as seen), as properties can't be set on
 * them. {@link: Object.objectify} can be used on exceptions to convert any that are primitives into their equivalent
 * object wrapper forms so that this check will always work. However, because we need to flag the exact object which
 * will get rethrown, and because that rethrowing happens outside of the event processing pipeline, the objectification
 * must be done before the exception captured.
 *
 * @param A thrown exception to check or flag as having been seen
 * @returns `true` if the exception has already been captured, `false` if not (with the side effect of marking it seen)
 */
function checkOrSetAlreadyCaught(exception) {
  // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
  if (exception && (exception ).__sentry_captured__) {
    return true;
  }

  try {
    // set it this way rather than by assignment so that it's not ennumerable and therefore isn't recorded by the
    // `ExtraErrorData` integration
    object.addNonEnumerableProperty(exception , '__sentry_captured__', true);
  } catch (err) {
    // `exception` is a primitive, so we can't mark it seen
  }

  return false;
}

/**
 * Checks whether the given input is already an array, and if it isn't, wraps it in one.
 *
 * @param maybeArray Input to turn into an array, if necessary
 * @returns The input, if already an array, or an array with the input as the only element, if not
 */
function arrayify(maybeArray) {
  return Array.isArray(maybeArray) ? maybeArray : [maybeArray];
}

exports.addContextToFrame = addContextToFrame;
exports.addExceptionMechanism = addExceptionMechanism;
exports.addExceptionTypeValue = addExceptionTypeValue;
exports.arrayify = arrayify;
exports.checkOrSetAlreadyCaught = checkOrSetAlreadyCaught;
exports.getEventDescription = getEventDescription;
exports.parseSemver = parseSemver;
exports.uuid4 = uuid4;


},{"./object.js":138,"./string.js":145,"./worldwide.js":151}],136:[function(require,module,exports){
(function (process){(function (){
Object.defineProperty(exports, '__esModule', { value: true });

const env = require('./env.js');

/**
 * NOTE: In order to avoid circular dependencies, if you add a function to this module and it needs to print something,
 * you must either a) use `console.log` rather than the logger, or b) put your function elsewhere.
 */

/**
 * Checks whether we're in the Node.js or Browser environment
 *
 * @returns Answer to given question
 */
function isNodeEnv() {
  // explicitly check for browser bundles as those can be optimized statically
  // by terser/rollup.
  return (
    !env.isBrowserBundle() &&
    Object.prototype.toString.call(typeof process !== 'undefined' ? process : 0) === '[object process]'
  );
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
 * Helper for dynamically loading module that should work with linked dependencies.
 * The problem is that we _should_ be using `require(require.resolve(moduleName, { paths: [cwd()] }))`
 * However it's _not possible_ to do that with Webpack, as it has to know all the dependencies during
 * build time. `require.resolve` is also not available in any other way, so we cannot create,
 * a fake helper like we do with `dynamicRequire`.
 *
 * We always prefer to use local package, thus the value is not returned early from each `try/catch` block.
 * That is to mimic the behavior of `require.resolve` exactly.
 *
 * @param moduleName module name to require
 * @returns possibly required module
 */
function loadModule(moduleName) {
  let mod;

  try {
    mod = dynamicRequire(module, moduleName);
  } catch (e) {
    // no-empty
  }

  try {
    const { cwd } = dynamicRequire(module, 'process');
    mod = dynamicRequire(module, `${cwd()}/node_modules/${moduleName}`) ;
  } catch (e) {
    // no-empty
  }

  return mod;
}

exports.dynamicRequire = dynamicRequire;
exports.isNodeEnv = isNodeEnv;
exports.loadModule = loadModule;


}).call(this)}).call(this,require('_process'))
},{"./env.js":127,"_process":152}],137:[function(require,module,exports){
(function (global){(function (){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');
const memo = require('./memo.js');
const object = require('./object.js');
const stacktrace = require('./stacktrace.js');

/**
 * Recursively normalizes the given object.
 *
 * - Creates a copy to prevent original input mutation
 * - Skips non-enumerable properties
 * - When stringifying, calls `toJSON` if implemented
 * - Removes circular references
 * - Translates non-serializable values (`undefined`/`NaN`/functions) to serializable format
 * - Translates known global objects/classes to a string representations
 * - Takes care of `Error` object serialization
 * - Optionally limits depth of final output
 * - Optionally limits number of properties/elements included in any single object/array
 *
 * @param input The object to be normalized.
 * @param depth The max depth to which to normalize the object. (Anything deeper stringified whole.)
 * @param maxProperties The max number of elements or properties to be included in any single array or
 * object in the normallized output.
 * @returns A normalized version of the object, or `"**non-serializable**"` if any errors are thrown during normalization.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalize(input, depth = +Infinity, maxProperties = +Infinity) {
  try {
    // since we're at the outermost level, we don't provide a key
    return visit('', input, depth, maxProperties);
  } catch (err) {
    return { ERROR: `**non-serializable** (${err})` };
  }
}

/** JSDoc */
function normalizeToSize(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  object,
  // Default Node.js REPL depth
  depth = 3,
  // 100kB, as 200kB is max payload size, so half sounds reasonable
  maxSize = 100 * 1024,
) {
  const normalized = normalize(object, depth);

  if (jsonSize(normalized) > maxSize) {
    return normalizeToSize(object, depth - 1, maxSize);
  }

  return normalized ;
}

/**
 * Visits a node to perform normalization on it
 *
 * @param key The key corresponding to the given node
 * @param value The node to be visited
 * @param depth Optional number indicating the maximum recursion depth
 * @param maxProperties Optional maximum number of properties/elements included in any single object/array
 * @param memo Optional Memo class handling decycling
 */
function visit(
  key,
  value,
  depth = +Infinity,
  maxProperties = +Infinity,
  memo$1 = memo.memoBuilder(),
) {
  const [memoize, unmemoize] = memo$1;

  // Get the simple cases out of the way first
  if (value === null || (['number', 'boolean', 'string'].includes(typeof value) && !is.isNaN(value))) {
    return value ;
  }

  const stringified = stringifyValue(key, value);

  // Anything we could potentially dig into more (objects or arrays) will have come back as `"[object XXXX]"`.
  // Everything else will have already been serialized, so if we don't see that pattern, we're done.
  if (!stringified.startsWith('[object ')) {
    return stringified;
  }

  // From here on, we can assert that `value` is either an object or an array.

  // Do not normalize objects that we know have already been normalized. As a general rule, the
  // "__sentry_skip_normalization__" property should only be used sparingly and only should only be set on objects that
  // have already been normalized.
  if ((value )['__sentry_skip_normalization__']) {
    return value ;
  }

  // We're also done if we've reached the max depth
  if (depth === 0) {
    // At this point we know `serialized` is a string of the form `"[object XXXX]"`. Clean it up so it's just `"[XXXX]"`.
    return stringified.replace('object ', '');
  }

  // If we've already visited this branch, bail out, as it's circular reference. If not, note that we're seeing it now.
  if (memoize(value)) {
    return '[Circular ~]';
  }

  // If the value has a `toJSON` method, we call it to extract more information
  const valueWithToJSON = value ;
  if (valueWithToJSON && typeof valueWithToJSON.toJSON === 'function') {
    try {
      const jsonValue = valueWithToJSON.toJSON();
      // We need to normalize the return value of `.toJSON()` in case it has circular references
      return visit('', jsonValue, depth - 1, maxProperties, memo$1);
    } catch (err) {
      // pass (The built-in `toJSON` failed, but we can still try to do it ourselves)
    }
  }

  // At this point we know we either have an object or an array, we haven't seen it before, and we're going to recurse
  // because we haven't yet reached the max depth. Create an accumulator to hold the results of visiting each
  // property/entry, and keep track of the number of items we add to it.
  const normalized = (Array.isArray(value) ? [] : {}) ;
  let numAdded = 0;

  // Before we begin, convert`Error` and`Event` instances into plain objects, since some of each of their relevant
  // properties are non-enumerable and otherwise would get missed.
  const visitable = object.convertToPlainObject(value );

  for (const visitKey in visitable) {
    // Avoid iterating over fields in the prototype if they've somehow been exposed to enumeration.
    if (!Object.prototype.hasOwnProperty.call(visitable, visitKey)) {
      continue;
    }

    if (numAdded >= maxProperties) {
      normalized[visitKey] = '[MaxProperties ~]';
      break;
    }

    // Recursively visit all the child nodes
    const visitValue = visitable[visitKey];
    normalized[visitKey] = visit(visitKey, visitValue, depth - 1, maxProperties, memo$1);

    numAdded++;
  }

  // Once we've visited all the branches, remove the parent from memo storage
  unmemoize(value);

  // Return accumulated values
  return normalized;
}

/**
 * Stringify the given value. Handles various known special values and types.
 *
 * Not meant to be used on simple primitives which already have a string representation, as it will, for example, turn
 * the number 1231 into "[Object Number]", nor on `null`, as it will throw.
 *
 * @param value The value to stringify
 * @returns A stringified representation of the given value
 */
function stringifyValue(
  key,
  // this type is a tiny bit of a cheat, since this function does handle NaN (which is technically a number), but for
  // our internal use, it'll do
  value,
) {
  try {
    if (key === 'domain' && value && typeof value === 'object' && (value )._events) {
      return '[Domain]';
    }

    if (key === 'domainEmitter') {
      return '[DomainEmitter]';
    }

    // It's safe to use `global`, `window`, and `document` here in this manner, as we are asserting using `typeof` first
    // which won't throw if they are not present.

    if (typeof global !== 'undefined' && value === global) {
      return '[Global]';
    }

    // eslint-disable-next-line no-restricted-globals
    if (typeof window !== 'undefined' && value === window) {
      return '[Window]';
    }

    // eslint-disable-next-line no-restricted-globals
    if (typeof document !== 'undefined' && value === document) {
      return '[Document]';
    }

    // React's SyntheticEvent thingy
    if (is.isSyntheticEvent(value)) {
      return '[SyntheticEvent]';
    }

    if (typeof value === 'number' && value !== value) {
      return '[NaN]';
    }

    // this catches `undefined` (but not `null`, which is a primitive and can be serialized on its own)
    if (value === void 0) {
      return '[undefined]';
    }

    if (typeof value === 'function') {
      return `[Function: ${stacktrace.getFunctionName(value)}]`;
    }

    if (typeof value === 'symbol') {
      return `[${String(value)}]`;
    }

    // stringified BigInts are indistinguishable from regular numbers, so we need to label them to avoid confusion
    if (typeof value === 'bigint') {
      return `[BigInt: ${String(value)}]`;
    }

    // Now that we've knocked out all the special cases and the primitives, all we have left are objects. Simply casting
    // them to strings means that instances of classes which haven't defined their `toStringTag` will just come out as
    // `"[object Object]"`. If we instead look at the constructor's name (which is the same as the name of the class),
    // we can make sure that only plain objects come out that way.
    return `[object ${(Object.getPrototypeOf(value) ).constructor.name}]`;
  } catch (err) {
    return `**non-serializable** (${err})`;
  }
}

/** Calculates bytes size of input string */
function utf8Length(value) {
  // eslint-disable-next-line no-bitwise
  return ~-encodeURI(value).split(/%..|./).length;
}

/** Calculates bytes size of input object */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function jsonSize(value) {
  return utf8Length(JSON.stringify(value));
}

exports.normalize = normalize;
exports.normalizeToSize = normalizeToSize;
exports.walk = visit;


}).call(this)}).call(this,typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : {})
},{"./is.js":132,"./memo.js":134,"./object.js":138,"./stacktrace.js":144}],138:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const browser = require('./browser.js');
const is = require('./is.js');
const string = require('./string.js');

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

  const original = source[name] ;
  const wrapped = replacementFactory(original) ;

  // Make sure it's a function first, as we need to attach an empty prototype for `defineProperties` to work
  // otherwise it'll throw "TypeError: Object.defineProperties called on non-object"
  if (typeof wrapped === 'function') {
    try {
      markFunctionWrapped(wrapped, original);
    } catch (_Oo) {
      // This can throw if multiple fill happens on a global object like XMLHttpRequest
      // Fixes https://github.com/getsentry/sentry-javascript/issues/2043
    }
  }

  source[name] = wrapped;
}

/**
 * Defines a non-enumerable property on the given object.
 *
 * @param obj The object on which to set the property
 * @param name The name of the property to be set
 * @param value The value to which to set the property
 */
function addNonEnumerableProperty(obj, name, value) {
  Object.defineProperty(obj, name, {
    // enumerable: false, // the default, so we can save on bundle size by not explicitly setting it
    value: value,
    writable: true,
    configurable: true,
  });
}

/**
 * Remembers the original function on the wrapped function and
 * patches up the prototype.
 *
 * @param wrapped the wrapper function
 * @param original the original function that gets wrapped
 */
function markFunctionWrapped(wrapped, original) {
  const proto = original.prototype || {};
  wrapped.prototype = original.prototype = proto;
  addNonEnumerableProperty(wrapped, '__sentry_original__', original);
}

/**
 * This extracts the original function if available.  See
 * `markFunctionWrapped` for more information.
 *
 * @param func the function to unwrap
 * @returns the unwrapped version of the function if available.
 */
function getOriginalFunction(func) {
  return func.__sentry_original__;
}

/**
 * Encodes given object into url-friendly format
 *
 * @param object An object that contains serializable values
 * @returns string Encoded
 */
function urlEncode(object) {
  return Object.keys(object)
    .map(key => `${encodeURIComponent(key)}=${encodeURIComponent(object[key])}`)
    .join('&');
}

/**
 * Transforms any `Error` or `Event` into a plain object with all of their enumerable properties, and some of their
 * non-enumerable properties attached.
 *
 * @param value Initial source that we have to transform in order for it to be usable by the serializer
 * @returns An Event or Error turned into an object - or the value argurment itself, when value is neither an Event nor
 *  an Error.
 */
function convertToPlainObject(
  value,
)

 {
  if (is.isError(value)) {
    return {
      message: value.message,
      name: value.name,
      stack: value.stack,
      ...getOwnProperties(value),
    };
  } else if (is.isEvent(value)) {
    const newObj

 = {
      type: value.type,
      target: serializeEventTarget(value.target),
      currentTarget: serializeEventTarget(value.currentTarget),
      ...getOwnProperties(value),
    };

    if (typeof CustomEvent !== 'undefined' && is.isInstanceOf(value, CustomEvent)) {
      newObj.detail = value.detail;
    }

    return newObj;
  } else {
    return value;
  }
}

/** Creates a string representation of the target of an `Event` object */
function serializeEventTarget(target) {
  try {
    return is.isElement(target) ? browser.htmlTreeAsString(target) : Object.prototype.toString.call(target);
  } catch (_oO) {
    return '<unknown>';
  }
}

/** Filters out all but an object's own properties */
function getOwnProperties(obj) {
  if (typeof obj === 'object' && obj !== null) {
    const extractedProps = {};
    for (const property in obj) {
      if (Object.prototype.hasOwnProperty.call(obj, property)) {
        extractedProps[property] = (obj )[property];
      }
    }
    return extractedProps;
  } else {
    return {};
  }
}

/**
 * Given any captured exception, extract its keys and create a sorted
 * and truncated list that will be used inside the event message.
 * eg. `Non-error exception captured with keys: foo, bar, baz`
 */
function extractExceptionKeysForMessage(exception, maxLength = 40) {
  const keys = Object.keys(convertToPlainObject(exception));
  keys.sort();

  if (!keys.length) {
    return '[object has no keys]';
  }

  if (keys[0].length >= maxLength) {
    return string.truncate(keys[0], maxLength);
  }

  for (let includedKeys = keys.length; includedKeys > 0; includedKeys--) {
    const serialized = keys.slice(0, includedKeys).join(', ');
    if (serialized.length > maxLength) {
      continue;
    }
    if (includedKeys === keys.length) {
      return serialized;
    }
    return string.truncate(serialized, maxLength);
  }

  return '';
}

/**
 * Given any object, return a new object having removed all fields whose value was `undefined`.
 * Works recursively on objects and arrays.
 *
 * Attention: This function keeps circular references in the returned object.
 */
function dropUndefinedKeys(inputValue) {
  // This map keeps track of what already visited nodes map to.
  // Our Set - based memoBuilder doesn't work here because we want to the output object to have the same circular
  // references as the input object.
  const memoizationMap = new Map();

  // This function just proxies `_dropUndefinedKeys` to keep the `memoBuilder` out of this function's API
  return _dropUndefinedKeys(inputValue, memoizationMap);
}

function _dropUndefinedKeys(inputValue, memoizationMap) {
  if (is.isPlainObject(inputValue)) {
    // If this node has already been visited due to a circular reference, return the object it was mapped to in the new object
    const memoVal = memoizationMap.get(inputValue);
    if (memoVal !== undefined) {
      return memoVal ;
    }

    const returnValue = {};
    // Store the mapping of this value in case we visit it again, in case of circular data
    memoizationMap.set(inputValue, returnValue);

    for (const key of Object.keys(inputValue)) {
      if (typeof inputValue[key] !== 'undefined') {
        returnValue[key] = _dropUndefinedKeys(inputValue[key], memoizationMap);
      }
    }

    return returnValue ;
  }

  if (Array.isArray(inputValue)) {
    // If this node has already been visited due to a circular reference, return the array it was mapped to in the new object
    const memoVal = memoizationMap.get(inputValue);
    if (memoVal !== undefined) {
      return memoVal ;
    }

    const returnValue = [];
    // Store the mapping of this value in case we visit it again, in case of circular data
    memoizationMap.set(inputValue, returnValue);

    inputValue.forEach((item) => {
      returnValue.push(_dropUndefinedKeys(item, memoizationMap));
    });

    return returnValue ;
  }

  return inputValue;
}

/**
 * Ensure that something is an object.
 *
 * Turns `undefined` and `null` into `String`s and all other primitives into instances of their respective wrapper
 * classes (String, Boolean, Number, etc.). Acts as the identity function on non-primitives.
 *
 * @param wat The subject of the objectification
 * @returns A version of `wat` which can safely be used with `Object` class methods
 */
function objectify(wat) {
  let objectified;
  switch (true) {
    case wat === undefined || wat === null:
      objectified = new String(wat);
      break;

    // Though symbols and bigints do have wrapper classes (`Symbol` and `BigInt`, respectively), for whatever reason
    // those classes don't have constructors which can be used with the `new` keyword. We therefore need to cast each as
    // an object in order to wrap it.
    case typeof wat === 'symbol' || typeof wat === 'bigint':
      objectified = Object(wat);
      break;

    // this will catch the remaining primitives: `String`, `Number`, and `Boolean`
    case is.isPrimitive(wat):
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      objectified = new (wat ).constructor(wat);
      break;

    // by process of elimination, at this point we know that `wat` must already be an object
    default:
      objectified = wat;
      break;
  }
  return objectified;
}

exports.addNonEnumerableProperty = addNonEnumerableProperty;
exports.convertToPlainObject = convertToPlainObject;
exports.dropUndefinedKeys = dropUndefinedKeys;
exports.extractExceptionKeysForMessage = extractExceptionKeysForMessage;
exports.fill = fill;
exports.getOriginalFunction = getOriginalFunction;
exports.markFunctionWrapped = markFunctionWrapped;
exports.objectify = objectify;
exports.urlEncode = urlEncode;


},{"./browser.js":110,"./is.js":132,"./string.js":145}],139:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// Slightly modified (no IE8 support, ES6) and transcribed to TypeScript
// https://raw.githubusercontent.com/calvinmetcalf/rollup-plugin-node-builtins/master/src/es6/path.js

/** JSDoc */
function normalizeArray(parts, allowAboveRoot) {
  // if the path tries to go above the root, `up` ends up > 0
  let up = 0;
  for (let i = parts.length - 1; i >= 0; i--) {
    const last = parts[i];
    if (last === '.') {
      parts.splice(i, 1);
    } else if (last === '..') {
      parts.splice(i, 1);
      up++;
    } else if (up) {
      parts.splice(i, 1);
      up--;
    }
  }

  // if the path is allowed to go above the root, restore leading ..s
  if (allowAboveRoot) {
    for (; up--; up) {
      parts.unshift('..');
    }
  }

  return parts;
}

// Split a filename into [root, dir, basename, ext], unix version
// 'root' is just a slash, or nothing.
const splitPathRe = /^(\/?|)([\s\S]*?)((?:\.{1,2}|[^/]+?|)(\.[^./]*|))(?:[/]*)$/;
/** JSDoc */
function splitPath(filename) {
  const parts = splitPathRe.exec(filename);
  return parts ? parts.slice(1) : [];
}

// path.resolve([from ...], to)
// posix version
/** JSDoc */
function resolve(...args) {
  let resolvedPath = '';
  let resolvedAbsolute = false;

  for (let i = args.length - 1; i >= -1 && !resolvedAbsolute; i--) {
    const path = i >= 0 ? args[i] : '/';

    // Skip empty entries
    if (!path) {
      continue;
    }

    resolvedPath = `${path}/${resolvedPath}`;
    resolvedAbsolute = path.charAt(0) === '/';
  }

  // At this point the path should be resolved to a full absolute path, but
  // handle relative paths to be safe (might happen when process.cwd() fails)

  // Normalize the path
  resolvedPath = normalizeArray(
    resolvedPath.split('/').filter(p => !!p),
    !resolvedAbsolute,
  ).join('/');

  return (resolvedAbsolute ? '/' : '') + resolvedPath || '.';
}

/** JSDoc */
function trim(arr) {
  let start = 0;
  for (; start < arr.length; start++) {
    if (arr[start] !== '') {
      break;
    }
  }

  let end = arr.length - 1;
  for (; end >= 0; end--) {
    if (arr[end] !== '') {
      break;
    }
  }

  if (start > end) {
    return [];
  }
  return arr.slice(start, end - start + 1);
}

// path.relative(from, to)
// posix version
/** JSDoc */
function relative(from, to) {
  /* eslint-disable no-param-reassign */
  from = resolve(from).substr(1);
  to = resolve(to).substr(1);
  /* eslint-enable no-param-reassign */

  const fromParts = trim(from.split('/'));
  const toParts = trim(to.split('/'));

  const length = Math.min(fromParts.length, toParts.length);
  let samePartsLength = length;
  for (let i = 0; i < length; i++) {
    if (fromParts[i] !== toParts[i]) {
      samePartsLength = i;
      break;
    }
  }

  let outputParts = [];
  for (let i = samePartsLength; i < fromParts.length; i++) {
    outputParts.push('..');
  }

  outputParts = outputParts.concat(toParts.slice(samePartsLength));

  return outputParts.join('/');
}

// path.normalize(path)
// posix version
/** JSDoc */
function normalizePath(path) {
  const isPathAbsolute = isAbsolute(path);
  const trailingSlash = path.substr(-1) === '/';

  // Normalize the path
  let normalizedPath = normalizeArray(
    path.split('/').filter(p => !!p),
    !isPathAbsolute,
  ).join('/');

  if (!normalizedPath && !isPathAbsolute) {
    normalizedPath = '.';
  }
  if (normalizedPath && trailingSlash) {
    normalizedPath += '/';
  }

  return (isPathAbsolute ? '/' : '') + normalizedPath;
}

// posix version
/** JSDoc */
function isAbsolute(path) {
  return path.charAt(0) === '/';
}

// posix version
/** JSDoc */
function join(...args) {
  return normalizePath(args.join('/'));
}

/** JSDoc */
function dirname(path) {
  const result = splitPath(path);
  const root = result[0];
  let dir = result[1];

  if (!root && !dir) {
    // No dirname whatsoever
    return '.';
  }

  if (dir) {
    // It has a dirname, strip trailing slash
    dir = dir.substr(0, dir.length - 1);
  }

  return root + dir;
}

/** JSDoc */
function basename(path, ext) {
  let f = splitPath(path)[2];
  if (ext && f.substr(ext.length * -1) === ext) {
    f = f.substr(0, f.length - ext.length);
  }
  return f;
}

exports.basename = basename;
exports.dirname = dirname;
exports.isAbsolute = isAbsolute;
exports.join = join;
exports.normalizePath = normalizePath;
exports.relative = relative;
exports.resolve = resolve;


},{}],140:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const error = require('./error.js');
const syncpromise = require('./syncpromise.js');

/**
 * Creates an new PromiseBuffer object with the specified limit
 * @param limit max number of promises that can be stored in the buffer
 */
function makePromiseBuffer(limit) {
  const buffer = [];

  function isReady() {
    return limit === undefined || buffer.length < limit;
  }

  /**
   * Remove a promise from the queue.
   *
   * @param task Can be any PromiseLike<T>
   * @returns Removed promise.
   */
  function remove(task) {
    return buffer.splice(buffer.indexOf(task), 1)[0];
  }

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
  function add(taskProducer) {
    if (!isReady()) {
      return syncpromise.rejectedSyncPromise(new error.SentryError('Not adding Promise because buffer limit was reached.'));
    }

    // start the task and add its promise to the queue
    const task = taskProducer();
    if (buffer.indexOf(task) === -1) {
      buffer.push(task);
    }
    void task
      .then(() => remove(task))
      // Use `then(null, rejectionHandler)` rather than `catch(rejectionHandler)` so that we can use `PromiseLike`
      // rather than `Promise`. `PromiseLike` doesn't have a `.catch` method, making its polyfill smaller. (ES5 didn't
      // have promises, so TS has to polyfill when down-compiling.)
      .then(null, () =>
        remove(task).then(null, () => {
          // We have to add another catch here because `remove()` starts a new promise chain.
        }),
      );
    return task;
  }

  /**
   * Wait for all promises in the queue to resolve or for timeout to expire, whichever comes first.
   *
   * @param timeout The time, in ms, after which to resolve to `false` if the queue is still non-empty. Passing `0` (or
   * not passing anything) will make the promise wait as long as it takes for the queue to drain before resolving to
   * `true`.
   * @returns A promise which will resolve to `true` if the queue is already empty or drains before the timeout, and
   * `false` otherwise
   */
  function drain(timeout) {
    return new syncpromise.SyncPromise((resolve, reject) => {
      let counter = buffer.length;

      if (!counter) {
        return resolve(true);
      }

      // wait for `timeout` ms and then resolve to `false` (if not cancelled first)
      const capturedSetTimeout = setTimeout(() => {
        if (timeout && timeout > 0) {
          resolve(false);
        }
      }, timeout);

      // if all promises resolve in time, cancel the timer and resolve to `true`
      buffer.forEach(item => {
        void syncpromise.resolvedSyncPromise(item).then(() => {
          if (!--counter) {
            clearTimeout(capturedSetTimeout);
            resolve(true);
          }
        }, reject);
      });
    });
  }

  return {
    $: buffer,
    add,
    drain,
  };
}

exports.makePromiseBuffer = makePromiseBuffer;


},{"./error.js":129,"./syncpromise.js":147}],141:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// Intentionally keeping the key broad, as we don't know for sure what rate limit headers get returned from backend

const DEFAULT_RETRY_AFTER = 60 * 1000; // 60 seconds

/**
 * Extracts Retry-After value from the request header or returns default value
 * @param header string representation of 'Retry-After' header
 * @param now current unix timestamp
 *
 */
function parseRetryAfterHeader(header, now = Date.now()) {
  const headerDelay = parseInt(`${header}`, 10);
  if (!isNaN(headerDelay)) {
    return headerDelay * 1000;
  }

  const headerDate = Date.parse(`${header}`);
  if (!isNaN(headerDate)) {
    return headerDate - now;
  }

  return DEFAULT_RETRY_AFTER;
}

/**
 * Gets the time that given category is disabled until for rate limiting
 */
function disabledUntil(limits, category) {
  return limits[category] || limits.all || 0;
}

/**
 * Checks if a category is rate limited
 */
function isRateLimited(limits, category, now = Date.now()) {
  return disabledUntil(limits, category) > now;
}

/**
 * Update ratelimits from incoming headers.
 * Returns true if headers contains a non-empty rate limiting header.
 */
function updateRateLimits(
  limits,
  { statusCode, headers },
  now = Date.now(),
) {
  const updatedRateLimits = {
    ...limits,
  };

  // "The name is case-insensitive."
  // https://developer.mozilla.org/en-US/docs/Web/API/Headers/get
  const rateLimitHeader = headers && headers['x-sentry-rate-limits'];
  const retryAfterHeader = headers && headers['retry-after'];

  if (rateLimitHeader) {
    /**
     * rate limit headers are of the form
     *     <header>,<header>,..
     * where each <header> is of the form
     *     <retry_after>: <categories>: <scope>: <reason_code>
     * where
     *     <retry_after> is a delay in seconds
     *     <categories> is the event type(s) (error, transaction, etc) being rate limited and is of the form
     *         <category>;<category>;...
     *     <scope> is what's being limited (org, project, or key) - ignored by SDK
     *     <reason_code> is an arbitrary string like "org_quota" - ignored by SDK
     */
    for (const limit of rateLimitHeader.trim().split(',')) {
      const [retryAfter, categories] = limit.split(':', 2);
      const headerDelay = parseInt(retryAfter, 10);
      const delay = (!isNaN(headerDelay) ? headerDelay : 60) * 1000; // 60sec default
      if (!categories) {
        updatedRateLimits.all = now + delay;
      } else {
        for (const category of categories.split(';')) {
          updatedRateLimits[category] = now + delay;
        }
      }
    }
  } else if (retryAfterHeader) {
    updatedRateLimits.all = now + parseRetryAfterHeader(retryAfterHeader, now);
  } else if (statusCode === 429) {
    updatedRateLimits.all = now + 60 * 1000;
  }

  return updatedRateLimits;
}

exports.DEFAULT_RETRY_AFTER = DEFAULT_RETRY_AFTER;
exports.disabledUntil = disabledUntil;
exports.isRateLimited = isRateLimited;
exports.parseRetryAfterHeader = parseRetryAfterHeader;
exports.updateRateLimits = updateRateLimits;


},{}],142:[function(require,module,exports){
var {
  _optionalChain
} = require('./buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');
const normalize = require('./normalize.js');
const url = require('./url.js');

const DEFAULT_INCLUDES = {
  ip: false,
  request: true,
  transaction: true,
  user: true,
};
const DEFAULT_REQUEST_INCLUDES = ['cookies', 'data', 'headers', 'method', 'query_string', 'url'];
const DEFAULT_USER_INCLUDES = ['id', 'username', 'email'];

/**
 * Sets parameterized route as transaction name e.g.: `GET /users/:id`
 * Also adds more context data on the transaction from the request
 */
function addRequestDataToTransaction(
  transaction,
  req,
  deps,
) {
  if (!transaction) return;
  if (!transaction.metadata.source || transaction.metadata.source === 'url') {
    // Attempt to grab a parameterized route off of the request
    transaction.setName(...extractPathForTransaction(req, { path: true, method: true }));
  }
  transaction.setData('url', req.originalUrl || req.url);
  if (req.baseUrl) {
    transaction.setData('baseUrl', req.baseUrl);
  }
  transaction.setData('query', extractQueryParams(req, deps));
}

/**
 * Extracts a complete and parameterized path from the request object and uses it to construct transaction name.
 * If the parameterized transaction name cannot be extracted, we fall back to the raw URL.
 *
 * Additionally, this function determines and returns the transaction name source
 *
 * eg. GET /mountpoint/user/:id
 *
 * @param req A request object
 * @param options What to include in the transaction name (method, path, or a custom route name to be
 *                used instead of the request's route)
 *
 * @returns A tuple of the fully constructed transaction name [0] and its source [1] (can be either 'route' or 'url')
 */
function extractPathForTransaction(
  req,
  options = {},
) {
  const method = req.method && req.method.toUpperCase();

  let path = '';
  let source = 'url';

  // Check to see if there's a parameterized route we can use (as there is in Express)
  if (options.customRoute || req.route) {
    path = options.customRoute || `${req.baseUrl || ''}${req.route && req.route.path}`;
    source = 'route';
  }

  // Otherwise, just take the original URL
  else if (req.originalUrl || req.url) {
    path = url.stripUrlQueryAndFragment(req.originalUrl || req.url || '');
  }

  let name = '';
  if (options.method && method) {
    name += method;
  }
  if (options.method && options.path) {
    name += ' ';
  }
  if (options.path && path) {
    name += path;
  }

  return [name, source];
}

/** JSDoc */
function extractTransaction(req, type) {
  switch (type) {
    case 'path': {
      return extractPathForTransaction(req, { path: true })[0];
    }
    case 'handler': {
      return (req.route && req.route.stack && req.route.stack[0] && req.route.stack[0].name) || '<anonymous>';
    }
    case 'methodPath':
    default: {
      return extractPathForTransaction(req, { path: true, method: true })[0];
    }
  }
}

/** JSDoc */
function extractUserData(
  user

,
  keys,
) {
  const extractedUser = {};
  const attributes = Array.isArray(keys) ? keys : DEFAULT_USER_INCLUDES;

  attributes.forEach(key => {
    if (user && key in user) {
      extractedUser[key] = user[key];
    }
  });

  return extractedUser;
}

/**
 * Normalize data from the request object, accounting for framework differences.
 *
 * @param req The request object from which to extract data
 * @param options.include An optional array of keys to include in the normalized data. Defaults to
 * DEFAULT_REQUEST_INCLUDES if not provided.
 * @param options.deps Injected, platform-specific dependencies
 * @returns An object containing normalized request data
 */
function extractRequestData(
  req,
  options

,
) {
  const { include = DEFAULT_REQUEST_INCLUDES, deps } = options || {};
  const requestData = {};

  // headers:
  //   node, express, koa, nextjs: req.headers
  const headers = (req.headers || {})

;
  // method:
  //   node, express, koa, nextjs: req.method
  const method = req.method;
  // host:
  //   express: req.hostname in > 4 and req.host in < 4
  //   koa: req.host
  //   node, nextjs: req.headers.host
  const host = req.hostname || req.host || headers.host || '<no host>';
  // protocol:
  //   node, nextjs: <n/a>
  //   express, koa: req.protocol
  const protocol = req.protocol === 'https' || (req.socket && req.socket.encrypted) ? 'https' : 'http';
  // url (including path and query string):
  //   node, express: req.originalUrl
  //   koa, nextjs: req.url
  const originalUrl = req.originalUrl || req.url || '';
  // absolute url
  const absoluteUrl = `${protocol}://${host}${originalUrl}`;
  include.forEach(key => {
    switch (key) {
      case 'headers': {
        requestData.headers = headers;
        break;
      }
      case 'method': {
        requestData.method = method;
        break;
      }
      case 'url': {
        requestData.url = absoluteUrl;
        break;
      }
      case 'cookies': {
        // cookies:
        //   node, express, koa: req.headers.cookie
        //   vercel, sails.js, express (w/ cookie middleware), nextjs: req.cookies
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        requestData.cookies =
          // TODO (v8 / #5257): We're only sending the empty object for backwards compatibility, so the last bit can
          // come off in v8
          req.cookies || (headers.cookie && deps && deps.cookie && deps.cookie.parse(headers.cookie)) || {};
        break;
      }
      case 'query_string': {
        // query string:
        //   node: req.url (raw)
        //   express, koa, nextjs: req.query
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        requestData.query_string = extractQueryParams(req, deps);
        break;
      }
      case 'data': {
        if (method === 'GET' || method === 'HEAD') {
          break;
        }
        // body data:
        //   express, koa, nextjs: req.body
        //
        //   when using node by itself, you have to read the incoming stream(see
        //   https://nodejs.dev/learn/get-http-request-body-data-using-nodejs); if a user is doing that, we can't know
        //   where they're going to store the final result, so they'll have to capture this data themselves
        if (req.body !== undefined) {
          requestData.data = is.isString(req.body) ? req.body : JSON.stringify(normalize.normalize(req.body));
        }
        break;
      }
      default: {
        if ({}.hasOwnProperty.call(req, key)) {
          requestData[key] = (req )[key];
        }
      }
    }
  });

  return requestData;
}

/**
 * Options deciding what parts of the request to use when enhancing an event
 */

/**
 * Add data from the given request to the given event
 *
 * @param event The event to which the request data will be added
 * @param req Request object
 * @param options.include Flags to control what data is included
 * @param options.deps Injected platform-specific dependencies
 * @hidden
 */
function addRequestDataToEvent(
  event,
  req,
  options,
) {
  const include = {
    ...DEFAULT_INCLUDES,
    ..._optionalChain([options, 'optionalAccess', _ => _.include]),
  };

  if (include.request) {
    const extractedRequestData = Array.isArray(include.request)
      ? extractRequestData(req, { include: include.request, deps: _optionalChain([options, 'optionalAccess', _2 => _2.deps]) })
      : extractRequestData(req, { deps: _optionalChain([options, 'optionalAccess', _3 => _3.deps]) });

    event.request = {
      ...event.request,
      ...extractedRequestData,
    };
  }

  if (include.user) {
    const extractedUser = req.user && is.isPlainObject(req.user) ? extractUserData(req.user, include.user) : {};

    if (Object.keys(extractedUser).length) {
      event.user = {
        ...event.user,
        ...extractedUser,
      };
    }
  }

  // client ip:
  //   node, nextjs: req.socket.remoteAddress
  //   express, koa: req.ip
  if (include.ip) {
    const ip = req.ip || (req.socket && req.socket.remoteAddress);
    if (ip) {
      event.user = {
        ...event.user,
        ip_address: ip,
      };
    }
  }

  if (include.transaction && !event.transaction) {
    // TODO do we even need this anymore?
    // TODO make this work for nextjs
    event.transaction = extractTransaction(req, include.transaction);
  }

  return event;
}

function extractQueryParams(
  req,
  deps,
) {
  // url (including path and query string):
  //   node, express: req.originalUrl
  //   koa, nextjs: req.url
  let originalUrl = req.originalUrl || req.url || '';

  if (!originalUrl) {
    return;
  }

  // The `URL` constructor can't handle internal URLs of the form `/some/path/here`, so stick a dummy protocol and
  // hostname on the beginning. Since the point here is just to grab the query string, it doesn't matter what we use.
  if (originalUrl.startsWith('/')) {
    originalUrl = `http://dogs.are.great${originalUrl}`;
  }

  return (
    req.query ||
    (typeof URL !== undefined && new URL(originalUrl).search.replace('?', '')) ||
    // In Node 8, `URL` isn't in the global scope, so we have to use the built-in module from Node
    (deps && deps.url && deps.url.parse(originalUrl).query) ||
    undefined
  );
}

exports.addRequestDataToEvent = addRequestDataToEvent;
exports.addRequestDataToTransaction = addRequestDataToTransaction;
exports.extractPathForTransaction = extractPathForTransaction;
exports.extractRequestData = extractRequestData;


},{"./buildPolyfills":124,"./is.js":132,"./normalize.js":137,"./url.js":150}],143:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// Note: Ideally the `SeverityLevel` type would be derived from `validSeverityLevels`, but that would mean either
//
// a) moving `validSeverityLevels` to `@sentry/types`,
// b) moving the`SeverityLevel` type here, or
// c) importing `validSeverityLevels` from here into `@sentry/types`.
//
// Option A would make `@sentry/types` a runtime dependency of `@sentry/utils` (not good), and options B and C would
// create a circular dependency between `@sentry/types` and `@sentry/utils` (also not good). So a TODO accompanying the
// type, reminding anyone who changes it to change this list also, will have to do.

const validSeverityLevels = ['fatal', 'error', 'warning', 'log', 'info', 'debug'];

/**
 * Converts a string-based level into a member of the deprecated {@link Severity} enum.
 *
 * @deprecated `severityFromString` is deprecated. Please use `severityLevelFromString` instead.
 *
 * @param level String representation of Severity
 * @returns Severity
 */
function severityFromString(level) {
  return severityLevelFromString(level) ;
}

/**
 * Converts a string-based level into a `SeverityLevel`, normalizing it along the way.
 *
 * @param level String representation of desired `SeverityLevel`.
 * @returns The `SeverityLevel` corresponding to the given string, or 'log' if the string isn't a valid level.
 */
function severityLevelFromString(level) {
  return (level === 'warn' ? 'warning' : validSeverityLevels.includes(level) ? level : 'log') ;
}

exports.severityFromString = severityFromString;
exports.severityLevelFromString = severityLevelFromString;
exports.validSeverityLevels = validSeverityLevels;


},{}],144:[function(require,module,exports){
var {
  _optionalChain
} = require('./buildPolyfills');

Object.defineProperty(exports, '__esModule', { value: true });

const STACKTRACE_LIMIT = 50;

/**
 * Creates a stack parser with the supplied line parsers
 *
 * StackFrames are returned in the correct order for Sentry Exception
 * frames and with Sentry SDK internal frames removed from the top and bottom
 *
 */
function createStackParser(...parsers) {
  const sortedParsers = parsers.sort((a, b) => a[0] - b[0]).map(p => p[1]);

  return (stack, skipFirst = 0) => {
    const frames = [];

    for (const line of stack.split('\n').slice(skipFirst)) {
      // https://github.com/getsentry/sentry-javascript/issues/5459
      // Remove webpack (error: *) wrappers
      const cleanedLine = line.replace(/\(error: (.*)\)/, '$1');

      for (const parser of sortedParsers) {
        const frame = parser(cleanedLine);

        if (frame) {
          frames.push(frame);
          break;
        }
      }
    }

    return stripSentryFramesAndReverse(frames);
  };
}

/**
 * Gets a stack parser implementation from Options.stackParser
 * @see Options
 *
 * If options contains an array of line parsers, it is converted into a parser
 */
function stackParserFromStackParserOptions(stackParser) {
  if (Array.isArray(stackParser)) {
    return createStackParser(...stackParser);
  }
  return stackParser;
}

/**
 * @hidden
 */
function stripSentryFramesAndReverse(stack) {
  if (!stack.length) {
    return [];
  }

  let localStack = stack;

  const firstFrameFunction = localStack[0].function || '';
  const lastFrameFunction = localStack[localStack.length - 1].function || '';

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
    .map(frame => ({
      ...frame,
      filename: frame.filename || localStack[0].filename,
      function: frame.function || '?',
    }))
    .reverse();
}

const defaultFunctionName = '<anonymous>';

/**
 * Safely extract function name from itself
 */
function getFunctionName(fn) {
  try {
    if (!fn || typeof fn !== 'function') {
      return defaultFunctionName;
    }
    return fn.name || defaultFunctionName;
  } catch (e) {
    // Just accessing custom props in some Selenium environments
    // can cause a "Permission denied" exception (see raven-js#495).
    return defaultFunctionName;
  }
}

// eslint-disable-next-line complexity
function node(getModule) {
  const FILENAME_MATCH = /^\s*[-]{4,}$/;
  const FULL_MATCH = /at (?:async )?(?:(.+?)\s+\()?(?:(.+):(\d+):(\d+)?|([^)]+))\)?/;

  // eslint-disable-next-line complexity
  return (line) => {
    if (line.match(FILENAME_MATCH)) {
      return {
        filename: line,
      };
    }

    const lineMatch = line.match(FULL_MATCH);
    if (!lineMatch) {
      return undefined;
    }

    let object;
    let method;
    let functionName;
    let typeName;
    let methodName;

    if (lineMatch[1]) {
      functionName = lineMatch[1];

      let methodStart = functionName.lastIndexOf('.');
      if (functionName[methodStart - 1] === '.') {
        methodStart--;
      }

      if (methodStart > 0) {
        object = functionName.substr(0, methodStart);
        method = functionName.substr(methodStart + 1);
        const objectEnd = object.indexOf('.Module');
        if (objectEnd > 0) {
          functionName = functionName.substr(objectEnd + 1);
          object = object.substr(0, objectEnd);
        }
      }
      typeName = undefined;
    }

    if (method) {
      typeName = object;
      methodName = method;
    }

    if (method === '<anonymous>') {
      methodName = undefined;
      functionName = undefined;
    }

    if (functionName === undefined) {
      methodName = methodName || '<anonymous>';
      functionName = typeName ? `${typeName}.${methodName}` : methodName;
    }

    const filename = _optionalChain([lineMatch, 'access', _ => _[2], 'optionalAccess', _2 => _2.startsWith, 'call', _3 => _3('file://')]) ? lineMatch[2].substr(7) : lineMatch[2];
    const isNative = lineMatch[5] === 'native';
    const isInternal =
      isNative || (filename && !filename.startsWith('/') && !filename.startsWith('.') && filename.indexOf(':\\') !== 1);

    // in_app is all that's not an internal Node function or a module within node_modules
    // note that isNative appears to return true even for node core libraries
    // see https://github.com/getsentry/raven-node/issues/176
    const in_app = !isInternal && filename !== undefined && !filename.includes('node_modules/');

    return {
      filename,
      module: _optionalChain([getModule, 'optionalCall', _4 => _4(filename)]),
      function: functionName,
      lineno: parseInt(lineMatch[3], 10) || undefined,
      colno: parseInt(lineMatch[4], 10) || undefined,
      in_app,
    };
  };
}

/**
 * Node.js stack line parser
 *
 * This is in @sentry/utils so it can be used from the Electron SDK in the browser for when `nodeIntegration == true`.
 * This allows it to be used without referencing or importing any node specific code which causes bundlers to complain
 */
function nodeStackLineParser(getModule) {
  return [90, node(getModule)];
}

exports.createStackParser = createStackParser;
exports.getFunctionName = getFunctionName;
exports.nodeStackLineParser = nodeStackLineParser;
exports.stackParserFromStackParserOptions = stackParserFromStackParserOptions;
exports.stripSentryFramesAndReverse = stripSentryFramesAndReverse;


},{"./buildPolyfills":124}],145:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');

/**
 * Truncates given string to the maximum characters count
 *
 * @param str An object that contains serializable values
 * @param max Maximum number of characters in truncated string (0 = unlimited)
 * @returns string Encoded
 */
function truncate(str, max = 0) {
  if (typeof str !== 'string' || max === 0) {
    return str;
  }
  return str.length <= max ? str : `${str.substr(0, max)}...`;
}

/**
 * This is basically just `trim_line` from
 * https://github.com/getsentry/sentry/blob/master/src/sentry/lang/javascript/processor.py#L67
 *
 * @param str An object that contains serializable values
 * @param max Maximum number of characters in truncated string
 * @returns string Encoded
 */
function snipLine(line, colno) {
  let newLine = line;
  const lineLength = newLine.length;
  if (lineLength <= 150) {
    return newLine;
  }
  if (colno > lineLength) {
    // eslint-disable-next-line no-param-reassign
    colno = lineLength;
  }

  let start = Math.max(colno - 60, 0);
  if (start < 5) {
    start = 0;
  }

  let end = Math.min(start + 140, lineLength);
  if (end > lineLength - 5) {
    end = lineLength;
  }
  if (end === lineLength) {
    start = Math.max(end - 140, 0);
  }

  newLine = newLine.slice(start, end);
  if (start > 0) {
    newLine = `'{snip} ${newLine}`;
  }
  if (end < lineLength) {
    newLine += ' {snip}';
  }

  return newLine;
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

  const output = [];
  // eslint-disable-next-line @typescript-eslint/prefer-for-of
  for (let i = 0; i < input.length; i++) {
    const value = input[i];
    try {
      output.push(String(value));
    } catch (e) {
      output.push('[value cannot be serialized]');
    }
  }

  return output.join(delimiter);
}

/**
 * Checks if the given value matches a regex or string
 *
 * @param value The string to test
 * @param pattern Either a regex or a string against which `value` will be matched
 * @param requireExactStringMatch If true, `value` must match `pattern` exactly. If false, `value` will match
 * `pattern` if it contains `pattern`. Only applies to string-type patterns.
 */
function isMatchingPattern(
  value,
  pattern,
  requireExactStringMatch = false,
) {
  if (!is.isString(value)) {
    return false;
  }

  if (is.isRegExp(pattern)) {
    return pattern.test(value);
  }
  if (is.isString(pattern)) {
    return requireExactStringMatch ? value === pattern : value.includes(pattern);
  }

  return false;
}

/**
 * Test the given string against an array of strings and regexes. By default, string matching is done on a
 * substring-inclusion basis rather than a strict equality basis
 *
 * @param testString The string to test
 * @param patterns The patterns against which to test the string
 * @param requireExactStringMatch If true, `testString` must match one of the given string patterns exactly in order to
 * count. If false, `testString` will match a string pattern if it contains that pattern.
 * @returns
 */
function stringMatchesSomePattern(
  testString,
  patterns = [],
  requireExactStringMatch = false,
) {
  return patterns.some(pattern => isMatchingPattern(testString, pattern, requireExactStringMatch));
}

/**
 * Given a string, escape characters which have meaning in the regex grammar, such that the result is safe to feed to
 * `new RegExp()`.
 *
 * Based on https://github.com/sindresorhus/escape-string-regexp. Vendored to a) reduce the size by skipping the runtime
 * type-checking, and b) ensure it gets down-compiled for old versions of Node (the published package only supports Node
 * 12+).
 *
 * @param regexString The string to escape
 * @returns An version of the string with all special regex characters escaped
 */
function escapeStringForRegex(regexString) {
  // escape the hyphen separately so we can also replace it with a unicode literal hyphen, to avoid the problems
  // discussed in https://github.com/sindresorhus/escape-string-regexp/issues/20.
  return regexString.replace(/[|\\{}()[\]^$+*?.]/g, '\\$&').replace(/-/g, '\\x2d');
}

exports.escapeStringForRegex = escapeStringForRegex;
exports.isMatchingPattern = isMatchingPattern;
exports.safeJoin = safeJoin;
exports.snipLine = snipLine;
exports.stringMatchesSomePattern = stringMatchesSomePattern;
exports.truncate = truncate;


},{"./is.js":132}],146:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const logger = require('./logger.js');
const worldwide = require('./worldwide.js');

// eslint-disable-next-line deprecation/deprecation
const WINDOW = worldwide.getGlobalObject();

/**
 * Tells whether current environment supports ErrorEvent objects
 * {@link supportsErrorEvent}.
 *
 * @returns Answer to the given question.
 */
function supportsErrorEvent() {
  try {
    new ErrorEvent('');
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Tells whether current environment supports DOMError objects
 * {@link supportsDOMError}.
 *
 * @returns Answer to the given question.
 */
function supportsDOMError() {
  try {
    // Chrome: VM89:1 Uncaught TypeError: Failed to construct 'DOMError':
    // 1 argument required, but only 0 present.
    // @ts-ignore It really needs 1 argument, not 0.
    new DOMError('');
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Tells whether current environment supports DOMException objects
 * {@link supportsDOMException}.
 *
 * @returns Answer to the given question.
 */
function supportsDOMException() {
  try {
    new DOMException('');
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Tells whether current environment supports Fetch API
 * {@link supportsFetch}.
 *
 * @returns Answer to the given question.
 */
function supportsFetch() {
  if (!('fetch' in WINDOW)) {
    return false;
  }

  try {
    new Headers();
    new Request('http://www.example.com');
    new Response();
    return true;
  } catch (e) {
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

  // Fast path to avoid DOM I/O
  // eslint-disable-next-line @typescript-eslint/unbound-method
  if (isNativeFetch(WINDOW.fetch)) {
    return true;
  }

  // window.fetch is implemented, but is polyfilled or already wrapped (e.g: by a chrome extension)
  // so create a "pure" iframe to see if that has native fetch
  let result = false;
  const doc = WINDOW.document;
  // eslint-disable-next-line deprecation/deprecation
  if (doc && typeof (doc.createElement ) === 'function') {
    try {
      const sandbox = doc.createElement('iframe');
      sandbox.hidden = true;
      doc.head.appendChild(sandbox);
      if (sandbox.contentWindow && sandbox.contentWindow.fetch) {
        // eslint-disable-next-line @typescript-eslint/unbound-method
        result = isNativeFetch(sandbox.contentWindow.fetch);
      }
      doc.head.removeChild(sandbox);
    } catch (err) {
      (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__) &&
        logger.logger.warn('Could not create sandbox iframe for pure fetch check, bailing to window.fetch: ', err);
    }
  }

  return result;
}

/**
 * Tells whether current environment supports ReportingObserver API
 * {@link supportsReportingObserver}.
 *
 * @returns Answer to the given question.
 */
function supportsReportingObserver() {
  return 'ReportingObserver' in WINDOW;
}

/**
 * Tells whether current environment supports Referrer Policy API
 * {@link supportsReferrerPolicy}.
 *
 * @returns Answer to the given question.
 */
function supportsReferrerPolicy() {
  // Despite all stars in the sky saying that Edge supports old draft syntax, aka 'never', 'always', 'origin' and 'default'
  // (see https://caniuse.com/#feat=referrer-policy),
  // it doesn't. And it throws an exception instead of ignoring this parameter...
  // REF: https://github.com/getsentry/raven-js/issues/1233

  if (!supportsFetch()) {
    return false;
  }

  try {
    new Request('_', {
      referrerPolicy: 'origin' ,
    });
    return true;
  } catch (e) {
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
  /* eslint-disable @typescript-eslint/no-unsafe-member-access */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chrome = (WINDOW ).chrome;
  const isChromePackagedApp = chrome && chrome.app && chrome.app.runtime;
  /* eslint-enable @typescript-eslint/no-unsafe-member-access */
  const hasHistoryApi = 'history' in WINDOW && !!WINDOW.history.pushState && !!WINDOW.history.replaceState;

  return !isChromePackagedApp && hasHistoryApi;
}

exports.isNativeFetch = isNativeFetch;
exports.supportsDOMError = supportsDOMError;
exports.supportsDOMException = supportsDOMException;
exports.supportsErrorEvent = supportsErrorEvent;
exports.supportsFetch = supportsFetch;
exports.supportsHistory = supportsHistory;
exports.supportsNativeFetch = supportsNativeFetch;
exports.supportsReferrerPolicy = supportsReferrerPolicy;
exports.supportsReportingObserver = supportsReportingObserver;


},{"./logger.js":133,"./worldwide.js":151}],147:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');

/* eslint-disable @typescript-eslint/explicit-function-return-type */

/** SyncPromise internal states */
var States; (function (States) {
  /** Pending */
  const PENDING = 0; States[States["PENDING"] = PENDING] = "PENDING";
  /** Resolved / OK */
  const RESOLVED = 1; States[States["RESOLVED"] = RESOLVED] = "RESOLVED";
  /** Rejected / Error */
  const REJECTED = 2; States[States["REJECTED"] = REJECTED] = "REJECTED";
})(States || (States = {}));

// Overloads so we can call resolvedSyncPromise without arguments and generic argument

/**
 * Creates a resolved sync promise.
 *
 * @param value the value to resolve the promise with
 * @returns the resolved sync promise
 */
function resolvedSyncPromise(value) {
  return new SyncPromise(resolve => {
    resolve(value);
  });
}

/**
 * Creates a rejected sync promise.
 *
 * @param value the value to reject the promise with
 * @returns the rejected sync promise
 */
function rejectedSyncPromise(reason) {
  return new SyncPromise((_, reject) => {
    reject(reason);
  });
}

/**
 * Thenable class that behaves like a Promise and follows it's interface
 * but is not async internally
 */
class SyncPromise {
   __init() {this._state = States.PENDING;}
   __init2() {this._handlers = [];}

   constructor(
    executor,
  ) {;SyncPromise.prototype.__init.call(this);SyncPromise.prototype.__init2.call(this);SyncPromise.prototype.__init3.call(this);SyncPromise.prototype.__init4.call(this);SyncPromise.prototype.__init5.call(this);SyncPromise.prototype.__init6.call(this);
    try {
      executor(this._resolve, this._reject);
    } catch (e) {
      this._reject(e);
    }
  }

  /** JSDoc */
   then(
    onfulfilled,
    onrejected,
  ) {
    return new SyncPromise((resolve, reject) => {
      this._handlers.push([
        false,
        result => {
          if (!onfulfilled) {
            // TODO: ¯\_(ツ)_/¯
            // TODO: FIXME
            resolve(result );
          } else {
            try {
              resolve(onfulfilled(result));
            } catch (e) {
              reject(e);
            }
          }
        },
        reason => {
          if (!onrejected) {
            reject(reason);
          } else {
            try {
              resolve(onrejected(reason));
            } catch (e) {
              reject(e);
            }
          }
        },
      ]);
      this._executeHandlers();
    });
  }

  /** JSDoc */
   catch(
    onrejected,
  ) {
    return this.then(val => val, onrejected);
  }

  /** JSDoc */
   finally(onfinally) {
    return new SyncPromise((resolve, reject) => {
      let val;
      let isRejected;

      return this.then(
        value => {
          isRejected = false;
          val = value;
          if (onfinally) {
            onfinally();
          }
        },
        reason => {
          isRejected = true;
          val = reason;
          if (onfinally) {
            onfinally();
          }
        },
      ).then(() => {
        if (isRejected) {
          reject(val);
          return;
        }

        resolve(val );
      });
    });
  }

  /** JSDoc */
    __init3() {this._resolve = (value) => {
    this._setResult(States.RESOLVED, value);
  };}

  /** JSDoc */
    __init4() {this._reject = (reason) => {
    this._setResult(States.REJECTED, reason);
  };}

  /** JSDoc */
    __init5() {this._setResult = (state, value) => {
    if (this._state !== States.PENDING) {
      return;
    }

    if (is.isThenable(value)) {
      void (value ).then(this._resolve, this._reject);
      return;
    }

    this._state = state;
    this._value = value;

    this._executeHandlers();
  };}

  /** JSDoc */
    __init6() {this._executeHandlers = () => {
    if (this._state === States.PENDING) {
      return;
    }

    const cachedHandlers = this._handlers.slice();
    this._handlers = [];

    cachedHandlers.forEach(handler => {
      if (handler[0]) {
        return;
      }

      if (this._state === States.RESOLVED) {
        // eslint-disable-next-line @typescript-eslint/no-floating-promises
        handler[1](this._value );
      }

      if (this._state === States.REJECTED) {
        handler[2](this._value);
      }

      handler[0] = true;
    });
  };}
}

exports.SyncPromise = SyncPromise;
exports.rejectedSyncPromise = rejectedSyncPromise;
exports.resolvedSyncPromise = resolvedSyncPromise;


},{"./is.js":132}],148:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const node = require('./node.js');
const worldwide = require('./worldwide.js');

// eslint-disable-next-line deprecation/deprecation
const WINDOW = worldwide.getGlobalObject();

/**
 * An object that can return the current timestamp in seconds since the UNIX epoch.
 */

/**
 * A TimestampSource implementation for environments that do not support the Performance Web API natively.
 *
 * Note that this TimestampSource does not use a monotonic clock. A call to `nowSeconds` may return a timestamp earlier
 * than a previously returned value. We do not try to emulate a monotonic behavior in order to facilitate debugging. It
 * is more obvious to explain "why does my span have negative duration" than "why my spans have zero duration".
 */
const dateTimestampSource = {
  nowSeconds: () => Date.now() / 1000,
};

/**
 * A partial definition of the [Performance Web API]{@link https://developer.mozilla.org/en-US/docs/Web/API/Performance}
 * for accessing a high-resolution monotonic clock.
 */

/**
 * Returns a wrapper around the native Performance API browser implementation, or undefined for browsers that do not
 * support the API.
 *
 * Wrapping the native API works around differences in behavior from different browsers.
 */
function getBrowserPerformance() {
  const { performance } = WINDOW;
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
  const timeOrigin = Date.now() - performance.now();

  return {
    now: () => performance.now(),
    timeOrigin,
  };
}

/**
 * Returns the native Performance API implementation from Node.js. Returns undefined in old Node.js versions that don't
 * implement the API.
 */
function getNodePerformance() {
  try {
    const perfHooks = node.dynamicRequire(module, 'perf_hooks') ;
    return perfHooks.performance;
  } catch (_) {
    return undefined;
  }
}

/**
 * The Performance API implementation for the current platform, if available.
 */
const platformPerformance = node.isNodeEnv() ? getNodePerformance() : getBrowserPerformance();

const timestampSource =
  platformPerformance === undefined
    ? dateTimestampSource
    : {
        nowSeconds: () => (platformPerformance.timeOrigin + platformPerformance.now()) / 1000,
      };

/**
 * Returns a timestamp in seconds since the UNIX epoch using the Date API.
 */
const dateTimestampInSeconds = dateTimestampSource.nowSeconds.bind(dateTimestampSource);

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
const timestampInSeconds = timestampSource.nowSeconds.bind(timestampSource);

// Re-exported with an old name for backwards-compatibility.
const timestampWithMs = timestampInSeconds;

/**
 * A boolean that is true when timestampInSeconds uses the Performance API to produce monotonic timestamps.
 */
const usingPerformanceAPI = platformPerformance !== undefined;

/**
 * Internal helper to store what is the source of browserPerformanceTimeOrigin below. For debugging only.
 */
exports._browserPerformanceTimeOriginMode = void 0;

/**
 * The number of milliseconds since the UNIX epoch. This value is only usable in a browser, and only when the
 * performance API is available.
 */
const browserPerformanceTimeOrigin = (() => {
  // Unfortunately browsers may report an inaccurate time origin data, through either performance.timeOrigin or
  // performance.timing.navigationStart, which results in poor results in performance data. We only treat time origin
  // data as reliable if they are within a reasonable threshold of the current time.

  const { performance } = WINDOW;
  if (!performance || !performance.now) {
    exports._browserPerformanceTimeOriginMode = 'none';
    return undefined;
  }

  const threshold = 3600 * 1000;
  const performanceNow = performance.now();
  const dateNow = Date.now();

  // if timeOrigin isn't available set delta to threshold so it isn't used
  const timeOriginDelta = performance.timeOrigin
    ? Math.abs(performance.timeOrigin + performanceNow - dateNow)
    : threshold;
  const timeOriginIsReliable = timeOriginDelta < threshold;

  // While performance.timing.navigationStart is deprecated in favor of performance.timeOrigin, performance.timeOrigin
  // is not as widely supported. Namely, performance.timeOrigin is undefined in Safari as of writing.
  // Also as of writing, performance.timing is not available in Web Workers in mainstream browsers, so it is not always
  // a valid fallback. In the absence of an initial time provided by the browser, fallback to the current time from the
  // Date API.
  // eslint-disable-next-line deprecation/deprecation
  const navigationStart = performance.timing && performance.timing.navigationStart;
  const hasNavigationStart = typeof navigationStart === 'number';
  // if navigationStart isn't available set delta to threshold so it isn't used
  const navigationStartDelta = hasNavigationStart ? Math.abs(navigationStart + performanceNow - dateNow) : threshold;
  const navigationStartIsReliable = navigationStartDelta < threshold;

  if (timeOriginIsReliable || navigationStartIsReliable) {
    // Use the more reliable time origin
    if (timeOriginDelta <= navigationStartDelta) {
      exports._browserPerformanceTimeOriginMode = 'timeOrigin';
      return performance.timeOrigin;
    } else {
      exports._browserPerformanceTimeOriginMode = 'navigationStart';
      return navigationStart;
    }
  }

  // Either both timeOrigin and navigationStart are skewed or neither is available, fallback to Date.
  exports._browserPerformanceTimeOriginMode = 'dateNow';
  return dateNow;
})();

exports.browserPerformanceTimeOrigin = browserPerformanceTimeOrigin;
exports.dateTimestampInSeconds = dateTimestampInSeconds;
exports.timestampInSeconds = timestampInSeconds;
exports.timestampWithMs = timestampWithMs;
exports.usingPerformanceAPI = usingPerformanceAPI;


},{"./node.js":136,"./worldwide.js":151}],149:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const TRACEPARENT_REGEXP = new RegExp(
  '^[ \\t]*' + // whitespace
    '([0-9a-f]{32})?' + // trace_id
    '-?([0-9a-f]{16})?' + // span_id
    '-?([01])?' + // sampled
    '[ \\t]*$', // whitespace
);

/**
 * Extract transaction context data from a `sentry-trace` header.
 *
 * @param traceparent Traceparent string
 *
 * @returns Object containing data from the header, or undefined if traceparent string is malformed
 */
function extractTraceparentData(traceparent) {
  const matches = traceparent.match(TRACEPARENT_REGEXP);

  if (!traceparent || !matches) {
    // empty string or no matches is invalid traceparent data
    return undefined;
  }

  let parentSampled;
  if (matches[3] === '1') {
    parentSampled = true;
  } else if (matches[3] === '0') {
    parentSampled = false;
  }

  return {
    traceId: matches[1],
    parentSampled,
    parentSpanId: matches[2],
  };
}

exports.TRACEPARENT_REGEXP = TRACEPARENT_REGEXP;
exports.extractTraceparentData = extractTraceparentData;


},{}],150:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Parses string form of URL into an object
 * // borrowed from https://tools.ietf.org/html/rfc3986#appendix-B
 * // intentionally using regex and not <a/> href parsing trick because React Native and other
 * // environments where DOM might not be available
 * @returns parsed URL object
 */
function parseUrl(url)

 {
  if (!url) {
    return {};
  }

  const match = url.match(/^(([^:/?#]+):)?(\/\/([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?$/);

  if (!match) {
    return {};
  }

  // coerce to undefined values to empty string so we don't get 'undefined'
  const query = match[6] || '';
  const fragment = match[8] || '';
  return {
    host: match[4],
    path: match[5],
    protocol: match[2],
    relative: match[5] + query + fragment, // everything minus origin
  };
}

/**
 * Strip the query string and fragment off of a given URL or path (if present)
 *
 * @param urlPath Full URL or path, including possible query string and/or fragment
 * @returns URL or path without query string or fragment
 */
function stripUrlQueryAndFragment(urlPath) {
  // eslint-disable-next-line no-useless-escape
  return urlPath.split(/[\?#]/, 1)[0];
}

/**
 * Returns number of URL segments of a passed string URL.
 */
function getNumberOfUrlSegments(url) {
  // split at '/' or at '\/' to split regex urls correctly
  return url.split(/\\?\//).filter(s => s.length > 0 && s !== ',').length;
}

exports.getNumberOfUrlSegments = getNumberOfUrlSegments;
exports.parseUrl = parseUrl;
exports.stripUrlQueryAndFragment = stripUrlQueryAndFragment;


},{}],151:[function(require,module,exports){
(function (global){(function (){
Object.defineProperty(exports, '__esModule', { value: true });

/** Internal global with common properties and Sentry extensions  */

// The code below for 'isGlobalObj' and 'GLOBAL_OBJ' was copied from core-js before modification
// https://github.com/zloirock/core-js/blob/1b944df55282cdc99c90db5f49eb0b6eda2cc0a3/packages/core-js/internals/global.js
// core-js has the following licence:
//
// Copyright (c) 2014-2022 Denis Pushkarev
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

/** Returns 'obj' if it's the global object, otherwise returns undefined */
function isGlobalObj(obj) {
  return obj && obj.Math == Math ? obj : undefined;
}

/** Get's the global object for the current JavaScript runtime */
const GLOBAL_OBJ =
  (typeof globalThis == 'object' && isGlobalObj(globalThis)) ||
  // eslint-disable-next-line no-restricted-globals
  (typeof window == 'object' && isGlobalObj(window)) ||
  (typeof self == 'object' && isGlobalObj(self)) ||
  (typeof global == 'object' && isGlobalObj(global)) ||
  (function () {
    return this;
  })() ||
  {};

/**
 * @deprecated Use GLOBAL_OBJ instead or WINDOW from @sentry/browser. This will be removed in v8
 */
function getGlobalObject() {
  return GLOBAL_OBJ ;
}

/**
 * Returns a global singleton contained in the global `__SENTRY__` object.
 *
 * If the singleton doesn't already exist in `__SENTRY__`, it will be created using the given factory
 * function and added to the `__SENTRY__` object.
 *
 * @param name name of the global singleton on __SENTRY__
 * @param creator creator Factory function to create the singleton if it doesn't already exist on `__SENTRY__`
 * @param obj (Optional) The global object on which to look for `__SENTRY__`, if not `GLOBAL_OBJ`'s return value
 * @returns the singleton
 */
function getGlobalSingleton(name, creator, obj) {
  const gbl = (obj || GLOBAL_OBJ) ;
  const __SENTRY__ = (gbl.__SENTRY__ = gbl.__SENTRY__ || {});
  const singleton = __SENTRY__[name] || (__SENTRY__[name] = creator());
  return singleton;
}

exports.GLOBAL_OBJ = GLOBAL_OBJ;
exports.getGlobalObject = getGlobalObject;
exports.getGlobalSingleton = getGlobalSingleton;


}).call(this)}).call(this,typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : {})
},{}],152:[function(require,module,exports){
// shim for using process in browser
var process = module.exports = {};

// cached from whatever global is present so that test runners that stub it
// don't break things.  But we need to wrap it in a try catch in case it is
// wrapped in strict mode code which doesn't define any globals.  It's inside a
// function because try/catches deoptimize in certain engines.

var cachedSetTimeout;
var cachedClearTimeout;

function defaultSetTimout() {
    throw new Error('setTimeout has not been defined');
}
function defaultClearTimeout () {
    throw new Error('clearTimeout has not been defined');
}
(function () {
    try {
        if (typeof setTimeout === 'function') {
            cachedSetTimeout = setTimeout;
        } else {
            cachedSetTimeout = defaultSetTimout;
        }
    } catch (e) {
        cachedSetTimeout = defaultSetTimout;
    }
    try {
        if (typeof clearTimeout === 'function') {
            cachedClearTimeout = clearTimeout;
        } else {
            cachedClearTimeout = defaultClearTimeout;
        }
    } catch (e) {
        cachedClearTimeout = defaultClearTimeout;
    }
} ())
function runTimeout(fun) {
    if (cachedSetTimeout === setTimeout) {
        //normal enviroments in sane situations
        return setTimeout(fun, 0);
    }
    // if setTimeout wasn't available but was latter defined
    if ((cachedSetTimeout === defaultSetTimout || !cachedSetTimeout) && setTimeout) {
        cachedSetTimeout = setTimeout;
        return setTimeout(fun, 0);
    }
    try {
        // when when somebody has screwed with setTimeout but no I.E. maddness
        return cachedSetTimeout(fun, 0);
    } catch(e){
        try {
            // When we are in I.E. but the script has been evaled so I.E. doesn't trust the global object when called normally
            return cachedSetTimeout.call(null, fun, 0);
        } catch(e){
            // same as above but when it's a version of I.E. that must have the global object for 'this', hopfully our context correct otherwise it will throw a global error
            return cachedSetTimeout.call(this, fun, 0);
        }
    }


}
function runClearTimeout(marker) {
    if (cachedClearTimeout === clearTimeout) {
        //normal enviroments in sane situations
        return clearTimeout(marker);
    }
    // if clearTimeout wasn't available but was latter defined
    if ((cachedClearTimeout === defaultClearTimeout || !cachedClearTimeout) && clearTimeout) {
        cachedClearTimeout = clearTimeout;
        return clearTimeout(marker);
    }
    try {
        // when when somebody has screwed with setTimeout but no I.E. maddness
        return cachedClearTimeout(marker);
    } catch (e){
        try {
            // When we are in I.E. but the script has been evaled so I.E. doesn't  trust the global object when called normally
            return cachedClearTimeout.call(null, marker);
        } catch (e){
            // same as above but when it's a version of I.E. that must have the global object for 'this', hopfully our context correct otherwise it will throw a global error.
            // Some versions of I.E. have different rules for clearTimeout vs setTimeout
            return cachedClearTimeout.call(this, marker);
        }
    }



}
var queue = [];
var draining = false;
var currentQueue;
var queueIndex = -1;

function cleanUpNextTick() {
    if (!draining || !currentQueue) {
        return;
    }
    draining = false;
    if (currentQueue.length) {
        queue = currentQueue.concat(queue);
    } else {
        queueIndex = -1;
    }
    if (queue.length) {
        drainQueue();
    }
}

function drainQueue() {
    if (draining) {
        return;
    }
    var timeout = runTimeout(cleanUpNextTick);
    draining = true;

    var len = queue.length;
    while(len) {
        currentQueue = queue;
        queue = [];
        while (++queueIndex < len) {
            if (currentQueue) {
                currentQueue[queueIndex].run();
            }
        }
        queueIndex = -1;
        len = queue.length;
    }
    currentQueue = null;
    draining = false;
    runClearTimeout(timeout);
}

process.nextTick = function (fun) {
    var args = new Array(arguments.length - 1);
    if (arguments.length > 1) {
        for (var i = 1; i < arguments.length; i++) {
            args[i - 1] = arguments[i];
        }
    }
    queue.push(new Item(fun, args));
    if (queue.length === 1 && !draining) {
        runTimeout(drainQueue);
    }
};

// v8 likes predictible objects
function Item(fun, array) {
    this.fun = fun;
    this.array = array;
}
Item.prototype.run = function () {
    this.fun.apply(null, this.array);
};
process.title = 'browser';
process.browser = true;
process.env = {};
process.argv = [];
process.version = ''; // empty string to avoid regexp issues
process.versions = {};

function noop() {}

process.on = noop;
process.addListener = noop;
process.once = noop;
process.off = noop;
process.removeListener = noop;
process.removeAllListeners = noop;
process.emit = noop;
process.prependListener = noop;
process.prependOnceListener = noop;

process.listeners = function (name) { return [] }

process.binding = function (name) {
    throw new Error('process.binding is not supported');
};

process.cwd = function () { return '/' };
process.chdir = function (dir) {
    throw new Error('process.chdir is not supported');
};
process.umask = function() { return 0; };

},{}]},{},[5])(5)
});
