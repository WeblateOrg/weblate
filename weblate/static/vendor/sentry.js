(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}else if(typeof define==="function"&&define.amd){define([],f)}else{var g;if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}else if(typeof self!=="undefined"){g=self}else{g=this}g.Sentry = f()}})(function(){var define,module,exports;return (function(){function r(e,n,t){function o(i,f){if(!n[i]){if(!e[i]){var c="function"==typeof require&&require;if(!f&&c)return c(i,!0);if(u)return u(i,!0);var a=new Error("Cannot find module '"+i+"'");throw a.code="MODULE_NOT_FOUND",a}var p=n[i]={exports:{}};e[i][0].call(p.exports,function(r){var n=e[i][1][r];return o(n||r)},p,p.exports,r,e,n,t)}return n[i].exports}for(var u="function"==typeof require&&require,i=0;i<t.length;i++)o(t[i]);return o}return r})()({1:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const core = require('@sentry/core');

// exporting a separate copy of `WINDOW` rather than exporting the one from `@sentry/browser`
// prevents the browser package from being bundled in the CDN bundle, and avoids a
// circular dependency between the browser and feedback packages
const WINDOW = utils.GLOBAL_OBJ ;

const LIGHT_BACKGROUND = '#ffffff';
const INHERIT = 'inherit';
const SUBMIT_COLOR = 'rgba(108, 95, 199, 1)';
const LIGHT_THEME = {
  fontFamily: "'Helvetica Neue', Arial, sans-serif",
  fontSize: '14px',

  background: LIGHT_BACKGROUND,
  backgroundHover: '#f6f6f7',
  foreground: '#2b2233',
  border: '1.5px solid rgba(41, 35, 47, 0.13)',
  boxShadow: '0px 4px 24px 0px rgba(43, 34, 51, 0.12)',

  success: '#268d75',
  error: '#df3338',

  submitBackground: 'rgba(88, 74, 192, 1)',
  submitBackgroundHover: SUBMIT_COLOR,
  submitBorder: SUBMIT_COLOR,
  submitOutlineFocus: '#29232f',
  submitForeground: LIGHT_BACKGROUND,
  submitForegroundHover: LIGHT_BACKGROUND,

  cancelBackground: 'transparent',
  cancelBackgroundHover: 'var(--background-hover)',
  cancelBorder: 'var(--border)',
  cancelOutlineFocus: 'var(--input-outline-focus)',
  cancelForeground: 'var(--foreground)',
  cancelForegroundHover: 'var(--foreground)',

  inputBackground: INHERIT,
  inputForeground: INHERIT,
  inputBorder: 'var(--border)',
  inputOutlineFocus: SUBMIT_COLOR,
};

const DEFAULT_THEME = {
  light: LIGHT_THEME,
  dark: {
    ...LIGHT_THEME,

    background: '#29232f',
    backgroundHover: '#352f3b',
    foreground: '#ebe6ef',
    border: '1.5px solid rgba(235, 230, 239, 0.15)',

    success: '#2da98c',
    error: '#f55459',
  },
};

const ACTOR_LABEL = 'Report a Bug';
const CANCEL_BUTTON_LABEL = 'Cancel';
const SUBMIT_BUTTON_LABEL = 'Send Bug Report';
const FORM_TITLE = 'Report a Bug';
const EMAIL_PLACEHOLDER = 'your.email@example.org';
const EMAIL_LABEL = 'Email';
const MESSAGE_PLACEHOLDER = "What's the bug? What did you expect?";
const MESSAGE_LABEL = 'Description';
const NAME_PLACEHOLDER = 'Your Name';
const NAME_LABEL = 'Name';
const SUCCESS_MESSAGE_TEXT = 'Thank you for your report!';

const FEEDBACK_WIDGET_SOURCE = 'widget';
const FEEDBACK_API_SOURCE = 'api';

/**
 * Prepare a feedback event & enrich it with the SDK metadata.
 */
async function prepareFeedbackEvent({
  client,
  scope,
  event,
}) {
  const eventHint = {};
  if (client.emit) {
    client.emit('preprocessEvent', event, eventHint);
  }

  const preparedEvent = (await core.prepareEvent(
    client.getOptions(),
    event,
    eventHint,
    scope,
    client,
  )) ;

  if (preparedEvent === null) {
    // Taken from baseclient's `_processEvent` method, where this is handled for errors/transactions
    client.recordDroppedEvent('event_processor', 'feedback', event);
    return null;
  }

  // This normally happens in browser client "_prepareEvent"
  // but since we do not use this private method from the client, but rather the plain import
  // we need to do this manually.
  preparedEvent.platform = preparedEvent.platform || 'javascript';

  return preparedEvent;
}

/**
 * Send feedback using transport
 */
async function sendFeedbackRequest(
  { feedback: { message, email, name, source, url } },
  { includeReplay = true } = {},
) {
  const hub = core.getCurrentHub();
  const client = hub.getClient();
  const transport = client && client.getTransport();
  const dsn = client && client.getDsn();

  if (!client || !transport || !dsn) {
    return;
  }

  const baseEvent = {
    contexts: {
      feedback: {
        contact_email: email,
        name,
        message,
        url,
        source,
      },
    },
    type: 'feedback',
  };

  return new Promise((resolve, reject) => {
    hub.withScope(async scope => {
      // No use for breadcrumbs in feedback
      scope.clearBreadcrumbs();

      if ([FEEDBACK_API_SOURCE, FEEDBACK_WIDGET_SOURCE].includes(String(source))) {
        scope.setLevel('info');
      }

      const feedbackEvent = await prepareFeedbackEvent({
        scope,
        client,
        event: baseEvent,
      });

      if (feedbackEvent === null) {
        resolve();
        return;
      }

      if (client && client.emit) {
        client.emit('beforeSendFeedback', feedbackEvent, { includeReplay: Boolean(includeReplay) });
      }

      const envelope = core.createEventEnvelope(
        feedbackEvent,
        dsn,
        client.getOptions()._metadata,
        client.getOptions().tunnel,
      );

      let response;

      try {
        response = await transport.send(envelope);
      } catch (err) {
        const error = new Error('Unable to send Feedback');

        try {
          // In case browsers don't allow this property to be writable
          // @ts-expect-error This needs lib es2022 and newer
          error.cause = err;
        } catch (e) {
          // nothing to do
        }
        reject(error);
      }

      // TODO (v8): we can remove this guard once transport.send's type signature doesn't include void anymore
      if (!response) {
        resolve(response);
        return;
      }

      // Require valid status codes, otherwise can assume feedback was not sent successfully
      if (typeof response.statusCode === 'number' && (response.statusCode < 200 || response.statusCode >= 300)) {
        reject(new Error('Unable to send Feedback'));
      }

      resolve(response);
    });
  });
}

/*
 * For reference, the fully built event looks something like this:
 * {
 *     "type": "feedback",
 *     "event_id": "d2132d31b39445f1938d7e21b6bf0ec4",
 *     "timestamp": 1597977777.6189718,
 *     "dist": "1.12",
 *     "platform": "javascript",
 *     "environment": "production",
 *     "release": 42,
 *     "tags": {"transaction": "/organizations/:orgId/performance/:eventSlug/"},
 *     "sdk": {"name": "name", "version": "version"},
 *     "user": {
 *         "id": "123",
 *         "username": "user",
 *         "email": "user@site.com",
 *         "ip_address": "192.168.11.12",
 *     },
 *     "request": {
 *         "url": None,
 *         "headers": {
 *             "user-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15"
 *         },
 *     },
 *     "contexts": {
 *         "feedback": {
 *             "message": "test message",
 *             "contact_email": "test@example.com",
 *             "type": "feedback",
 *         },
 *         "trace": {
 *             "trace_id": "4C79F60C11214EB38604F4AE0781BFB2",
 *             "span_id": "FA90FDEAD5F74052",
 *             "type": "trace",
 *         },
 *         "replay": {
 *             "replay_id": "e2d42047b1c5431c8cba85ee2a8ab25d",
 *         },
 *     },
 *   }
 */

/**
 * Public API to send a Feedback item to Sentry
 */
function sendFeedback(
  { name, email, message, source = FEEDBACK_API_SOURCE, url = utils.getLocationHref() },
  options = {},
) {
  if (!message) {
    throw new Error('Unable to submit feedback with empty message');
  }

  return sendFeedbackRequest(
    {
      feedback: {
        name,
        email,
        message,
        url,
        source,
      },
    },
    options,
  );
}

/**
 * This serves as a build time flag that will be true by default, but false in non-debug builds or if users replace `__SENTRY_DEBUG__` in their generated code.
 *
 * ATTENTION: This constant must never cross package boundaries (i.e. be exported) to guarantee that it can be used for tree shaking.
 */
const DEBUG_BUILD = (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__);

/**
 * Quick and dirty deep merge for the Feedback integration options
 */
function mergeOptions(
  defaultOptions,
  optionOverrides,
) {
  return {
    ...defaultOptions,
    ...optionOverrides,
    themeDark: {
      ...defaultOptions.themeDark,
      ...optionOverrides.themeDark,
    },
    themeLight: {
      ...defaultOptions.themeLight,
      ...optionOverrides.themeLight,
    },
  };
}

/**
 * Creates <style> element for widget actor (button that opens the dialog)
 */
function createActorStyles(d) {
  const style = d.createElement('style');
  style.textContent = `
.widget__actor {
  line-height: 25px;

  display: flex;
  align-items: center;
  gap: 8px;

  border-radius: 12px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  padding: 12px 16px;
  text-decoration: none;
  z-index: 9000;

  color: var(--foreground);
  background-color: var(--background);
  border: var(--border);
  box-shadow: var(--box-shadow);
  opacity: 1;
  transition: opacity 0.1s ease-in-out;
}

.widget__actor:hover {
  background-color: var(--background-hover);
}

.widget__actor svg {
  width: 16px;
  height: 16px;
}

.widget__actor--hidden {
  opacity: 0;
  pointer-events: none;
  visibility: hidden;
}

.widget__actor__text {
}

.feedback-icon path {
  fill: var(--foreground);
}
`;

  return style;
}

/**
 * Creates <style> element for widget dialog
 */
function createDialogStyles(d) {
  const style = d.createElement('style');

  style.textContent = `
.dialog {
  line-height: 25px;
  background-color: rgba(0, 0, 0, 0.05);
  border: none;
  position: fixed;
  inset: 0;
  z-index: 10000;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 1;
  transition: opacity 0.2s ease-in-out;
}

.dialog:not([open]) {
  opacity: 0;
  pointer-events: none;
  visibility: hidden;
}
.dialog:not([open]) .dialog__content {
  transform: translate(0, -16px) scale(0.98);
}

.dialog__content {
  position: fixed;
  left: var(--left);
  right: var(--right);
  bottom: var(--bottom);
  top: var(--top);

  border: var(--border);
  border-radius: 20px;
  background-color: var(--background);
  color: var(--foreground);

  width: 320px;
  max-width: 100%;
  max-height: calc(100% - 2rem);
  display: flex;
  flex-direction: column;
  box-shadow: var(--box-shadow);
  transition: transform 0.2s ease-in-out;
  transform: translate(0, 0) scale(1);
}

.dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 20px;
  font-weight: 600;
  padding: 24px 24px 0 24px;
  margin: 0;
  margin-bottom: 16px;
}

.brand-link {
  display: inline-flex;
}

.error {
  color: var(--error);
  margin-bottom: 16px;
}

.form {
  display: grid;
  overflow: auto;
  flex-direction: column;
  gap: 16px;
  padding: 0 24px 24px;
}

.form__error-container {
  color: var(--error);
}

.form__error-container--hidden {
  display: none;
}

.form__label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0px;
}

.form__label__text {
  display: grid;
  gap: 4px;
  align-items: center;
  grid-auto-flow: column;
  grid-auto-columns: max-content;
}

.form__label__text--required {
  font-size: 0.85em;
}

.form__input {
  font-family: inherit;
  line-height: inherit;
  background-color: var(--input-background);
  box-sizing: border-box;
  border: var(--input-border);
  border-radius: 6px;
  color: var(--input-foreground);
  font-size: 14px;
  font-weight: 500;
  padding: 6px 12px;
}

.form__input:focus-visible {
  outline: 1px auto var(--input-outline-focus);
}

.form__input--textarea {
  font-family: inherit;
  resize: vertical;
}

.btn-group {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.btn {
  line-height: inherit;
  border: var(--cancel-border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  padding: 6px 16px;
}
.btn[disabled] {
  opacity: 0.6;
  pointer-events: none;
}

.btn--primary {
  background-color: var(--submit-background);
  border-color: var(--submit-border);
  color: var(--submit-foreground);
}
.btn--primary:hover {
  background-color: var(--submit-background-hover);
  color: var(--submit-foreground-hover);
}
.btn--primary:focus-visible {
  outline: 1px auto var(--submit-outline-focus);
}

.btn--default {
  background-color: var(--cancel-background);
  color: var(--cancel-foreground);
  font-weight: 500;
}
.btn--default:hover {
  background-color: var(--cancel-background-hover);
  color: var(--cancel-foreground-hover);
}
.btn--default:focus-visible {
  outline: 1px auto var(--cancel-outline-focus);
}

.success-message {
  background-color: var(--background);
  border: var(--border);
  border-radius: 12px;
  box-shadow: var(--box-shadow);
  font-weight: 600;
  color: var(--success);
  padding: 12px 24px;
  line-height: 25px;
  display: grid;
  align-items: center;
  grid-auto-flow: column;
  gap: 6px;
  cursor: default;
}

.success-icon path {
  fill: var(--success);
}
`;

  return style;
}

function getThemedCssVariables(theme) {
  return `
  --background: ${theme.background};
  --background-hover: ${theme.backgroundHover};
  --foreground: ${theme.foreground};
  --error: ${theme.error};
  --success: ${theme.success};
  --border: ${theme.border};
  --box-shadow: ${theme.boxShadow};

  --submit-background: ${theme.submitBackground};
  --submit-background-hover: ${theme.submitBackgroundHover};
  --submit-border: ${theme.submitBorder};
  --submit-outline-focus: ${theme.submitOutlineFocus};
  --submit-foreground: ${theme.submitForeground};
  --submit-foreground-hover: ${theme.submitForegroundHover};

  --cancel-background: ${theme.cancelBackground};
  --cancel-background-hover: ${theme.cancelBackgroundHover};
  --cancel-border: ${theme.cancelBorder};
  --cancel-outline-focus: ${theme.cancelOutlineFocus};
  --cancel-foreground: ${theme.cancelForeground};
  --cancel-foreground-hover: ${theme.cancelForegroundHover};

  --input-background: ${theme.inputBackground};
  --input-foreground: ${theme.inputForeground};
  --input-border: ${theme.inputBorder};
  --input-outline-focus: ${theme.inputOutlineFocus};
  `;
}

/**
 * Creates <style> element for widget actor (button that opens the dialog)
 */
function createMainStyles(
  d,
  colorScheme,
  themes,
) {
  const style = d.createElement('style');
  style.textContent = `
:host {
  --bottom: 1rem;
  --right: 1rem;
  --top: auto;
  --left: auto;
  --z-index: 100000;
  --font-family: ${themes.light.fontFamily};
  --font-size: ${themes.light.fontSize};

  position: fixed;
  left: var(--left);
  right: var(--right);
  bottom: var(--bottom);
  top: var(--top);
  z-index: var(--z-index);

  font-family: var(--font-family);
  font-size: var(--font-size);

  ${getThemedCssVariables(colorScheme === 'dark' ? themes.dark : themes.light)}
}

${
  colorScheme === 'system'
    ? `
@media (prefers-color-scheme: dark) {
  :host {
    ${getThemedCssVariables(themes.dark)}
  }
}`
    : ''
}
}`;

  return style;
}

/**
 * Creates shadow host
 */
function createShadowHost({ id, colorScheme, themeDark, themeLight })

 {
  try {
    const doc = WINDOW.document;

    // Create the host
    const host = doc.createElement('div');
    host.id = id;

    // Create the shadow root
    const shadow = host.attachShadow({ mode: 'open' });

    shadow.appendChild(createMainStyles(doc, colorScheme, { dark: themeDark, light: themeLight }));
    shadow.appendChild(createDialogStyles(doc));

    return { shadow, host };
  } catch (e) {
    // Shadow DOM probably not supported
    utils.logger.warn('[Feedback] Browser does not support shadow DOM API');
    throw new Error('Browser does not support shadow DOM API.');
  }
}

/**
 * Handles UI behavior of dialog when feedback is submitted, calls
 * `sendFeedback` to send feedback.
 */
async function handleFeedbackSubmit(
  dialog,
  feedback,
  options,
) {
  if (!dialog) {
    // Not sure when this would happen
    return;
  }

  const showFetchError = () => {
    if (!dialog) {
      return;
    }
    dialog.showError('There was a problem submitting feedback, please wait and try again.');
  };

  dialog.hideError();

  try {
    const resp = await sendFeedback({ ...feedback, source: FEEDBACK_WIDGET_SOURCE }, options);

    // Success!
    return resp;
  } catch (err) {
    DEBUG_BUILD && utils.logger.error(err);
    showFetchError();
  }
}

/**
 * Helper function to set a dict of attributes on element (w/ specified namespace)
 */
function setAttributesNS(el, attributes) {
  Object.entries(attributes).forEach(([key, val]) => {
    el.setAttributeNS(null, key, val);
  });
  return el;
}

const SIZE = 20;
const XMLNS$2 = 'http://www.w3.org/2000/svg';

/**
 * Feedback Icon
 */
function Icon() {
  const createElementNS = (tagName) =>
    WINDOW.document.createElementNS(XMLNS$2, tagName);
  const svg = setAttributesNS(createElementNS('svg'), {
    class: 'feedback-icon',
    width: `${SIZE}`,
    height: `${SIZE}`,
    viewBox: `0 0 ${SIZE} ${SIZE}`,
    fill: 'none',
  });

  const g = setAttributesNS(createElementNS('g'), {
    clipPath: 'url(#clip0_57_80)',
  });

  const path = setAttributesNS(createElementNS('path'), {
    ['fill-rule']: 'evenodd',
    ['clip-rule']: 'evenodd',
    d: 'M15.6622 15H12.3997C12.2129 14.9959 12.031 14.9396 11.8747 14.8375L8.04965 12.2H7.49956V19.1C7.4875 19.3348 7.3888 19.5568 7.22256 19.723C7.05632 19.8892 6.83435 19.9879 6.59956 20H2.04956C1.80193 19.9968 1.56535 19.8969 1.39023 19.7218C1.21511 19.5467 1.1153 19.3101 1.11206 19.0625V12.2H0.949652C0.824431 12.2017 0.700142 12.1783 0.584123 12.1311C0.468104 12.084 0.362708 12.014 0.274155 11.9255C0.185602 11.8369 0.115689 11.7315 0.0685419 11.6155C0.0213952 11.4995 -0.00202913 11.3752 -0.00034808 11.25V3.75C-0.00900498 3.62067 0.0092504 3.49095 0.0532651 3.36904C0.0972798 3.24712 0.166097 3.13566 0.255372 3.04168C0.344646 2.94771 0.452437 2.87327 0.571937 2.82307C0.691437 2.77286 0.82005 2.74798 0.949652 2.75H8.04965L11.8747 0.1625C12.031 0.0603649 12.2129 0.00407221 12.3997 0H15.6622C15.9098 0.00323746 16.1464 0.103049 16.3215 0.278167C16.4966 0.453286 16.5964 0.689866 16.5997 0.9375V3.25269C17.3969 3.42959 18.1345 3.83026 18.7211 4.41679C19.5322 5.22788 19.9878 6.32796 19.9878 7.47502C19.9878 8.62209 19.5322 9.72217 18.7211 10.5333C18.1345 11.1198 17.3969 11.5205 16.5997 11.6974V14.0125C16.6047 14.1393 16.5842 14.2659 16.5395 14.3847C16.4948 14.5035 16.4268 14.6121 16.3394 14.7042C16.252 14.7962 16.147 14.8698 16.0307 14.9206C15.9144 14.9714 15.7891 14.9984 15.6622 15ZM1.89695 10.325H1.88715V4.625H8.33715C8.52423 4.62301 8.70666 4.56654 8.86215 4.4625L12.6872 1.875H14.7247V13.125H12.6872L8.86215 10.4875C8.70666 10.3835 8.52423 10.327 8.33715 10.325H2.20217C2.15205 10.3167 2.10102 10.3125 2.04956 10.3125C1.9981 10.3125 1.94708 10.3167 1.89695 10.325ZM2.98706 12.2V18.1625H5.66206V12.2H2.98706ZM16.5997 9.93612V5.01393C16.6536 5.02355 16.7072 5.03495 16.7605 5.04814C17.1202 5.13709 17.4556 5.30487 17.7425 5.53934C18.0293 5.77381 18.2605 6.06912 18.4192 6.40389C18.578 6.73866 18.6603 7.10452 18.6603 7.47502C18.6603 7.84552 18.578 8.21139 18.4192 8.54616C18.2605 8.88093 18.0293 9.17624 17.7425 9.41071C17.4556 9.64518 17.1202 9.81296 16.7605 9.90191C16.7072 9.91509 16.6536 9.9265 16.5997 9.93612Z',
  });
  svg.appendChild(g).appendChild(path);

  const speakerDefs = createElementNS('defs');
  const speakerClipPathDef = setAttributesNS(createElementNS('clipPath'), {
    id: 'clip0_57_80',
  });

  const speakerRect = setAttributesNS(createElementNS('rect'), {
    width: `${SIZE}`,
    height: `${SIZE}`,
    fill: 'white',
  });

  speakerClipPathDef.appendChild(speakerRect);
  speakerDefs.appendChild(speakerClipPathDef);

  svg.appendChild(speakerDefs).appendChild(speakerClipPathDef).appendChild(speakerRect);

  return {
    get el() {
      return svg;
    },
  };
}

/**
 * Helper function to create an element. Could be used as a JSX factory
 * (i.e. React-like syntax).
 */
function createElement(
  tagName,
  attributes,
  ...children
) {
  const doc = WINDOW.document;
  const element = doc.createElement(tagName);

  if (attributes) {
    Object.entries(attributes).forEach(([attribute, attributeValue]) => {
      if (attribute === 'className' && typeof attributeValue === 'string') {
        // JSX does not allow class as a valid name
        element.setAttribute('class', attributeValue);
      } else if (typeof attributeValue === 'boolean' && attributeValue) {
        element.setAttribute(attribute, '');
      } else if (typeof attributeValue === 'string') {
        element.setAttribute(attribute, attributeValue);
      } else if (attribute.startsWith('on') && typeof attributeValue === 'function') {
        element.addEventListener(attribute.substring(2).toLowerCase(), attributeValue);
      }
    });
  }
  for (const child of children) {
    appendChild(element, child);
  }

  return element;
}

function appendChild(parent, child) {
  const doc = WINDOW.document;
  if (typeof child === 'undefined' || child === null) {
    return;
  }

  if (Array.isArray(child)) {
    for (const value of child) {
      appendChild(parent, value);
    }
  } else if (child === false) ; else if (typeof child === 'string') {
    parent.appendChild(doc.createTextNode(child));
  } else if (child instanceof Node) {
    parent.appendChild(child);
  } else {
    parent.appendChild(doc.createTextNode(String(child)));
  }
}

/**
 *
 */
function Actor({ buttonLabel, onClick }) {
  function _handleClick(e) {
    onClick && onClick(e);
  }

  const el = createElement(
    'button',
    {
      type: 'button',
      className: 'widget__actor',
      ['aria-label']: buttonLabel,
      ['aria-hidden']: 'false',
    },
    Icon().el,
    buttonLabel
      ? createElement(
          'span',
          {
            className: 'widget__actor__text',
          },
          buttonLabel,
        )
      : null,
  );

  el.addEventListener('click', _handleClick);

  return {
    get el() {
      return el;
    },
    show: () => {
      el.classList.remove('widget__actor--hidden');
      el.setAttribute('aria-hidden', 'false');
    },
    hide: () => {
      el.classList.add('widget__actor--hidden');
      el.setAttribute('aria-hidden', 'true');
    },
  };
}

/**
 *
 */
function SubmitButton({ label }) {
  const el = createElement(
    'button',
    {
      type: 'submit',
      className: 'btn btn--primary',
      ['aria-label']: label,
    },
    label,
  );

  return {
    el,
  };
}

function retrieveStringValue(formData, key) {
  const value = formData.get(key);
  if (typeof value === 'string') {
    return value.trim();
  }
  return '';
}

/**
 * Creates the form element
 */
function Form({
  nameLabel,
  namePlaceholder,
  emailLabel,
  emailPlaceholder,
  messageLabel,
  messagePlaceholder,
  cancelButtonLabel,
  submitButtonLabel,

  showName,
  showEmail,
  isNameRequired,
  isEmailRequired,

  defaultName,
  defaultEmail,
  onCancel,
  onSubmit,
}) {
  const { el: submitEl } = SubmitButton({
    label: submitButtonLabel,
  });

  function handleSubmit(e) {
    e.preventDefault();

    if (!(e.target instanceof HTMLFormElement)) {
      return;
    }

    try {
      if (onSubmit) {
        const formData = new FormData(e.target );
        const feedback = {
          name: retrieveStringValue(formData, 'name'),
          email: retrieveStringValue(formData, 'email'),
          message: retrieveStringValue(formData, 'message'),
        };

        onSubmit(feedback);
      }
    } catch (e2) {
      // pass
    }
  }

  const errorEl = createElement('div', {
    className: 'form__error-container form__error-container--hidden',
    ['aria-hidden']: 'true',
  });

  function showError(message) {
    errorEl.textContent = message;
    errorEl.classList.remove('form__error-container--hidden');
    errorEl.setAttribute('aria-hidden', 'false');
  }

  function hideError() {
    errorEl.textContent = '';
    errorEl.classList.add('form__error-container--hidden');
    errorEl.setAttribute('aria-hidden', 'true');
  }

  const nameEl = createElement('input', {
    id: 'name',
    type: showName ? 'text' : 'hidden',
    ['aria-hidden']: showName ? 'false' : 'true',
    name: 'name',
    required: isNameRequired,
    className: 'form__input',
    placeholder: namePlaceholder,
    value: defaultName,
  });

  const emailEl = createElement('input', {
    id: 'email',
    type: showEmail ? 'text' : 'hidden',
    ['aria-hidden']: showEmail ? 'false' : 'true',
    name: 'email',
    required: isEmailRequired,
    className: 'form__input',
    placeholder: emailPlaceholder,
    value: defaultEmail,
  });

  const messageEl = createElement('textarea', {
    id: 'message',
    autoFocus: 'true',
    rows: '5',
    name: 'message',
    required: true,
    className: 'form__input form__input--textarea',
    placeholder: messagePlaceholder,
  });

  const cancelEl = createElement(
    'button',
    {
      type: 'button',
      className: 'btn btn--default',
      ['aria-label']: cancelButtonLabel,
      onClick: (e) => {
        onCancel && onCancel(e);
      },
    },
    cancelButtonLabel,
  );

  const formEl = createElement(
    'form',
    {
      className: 'form',
      onSubmit: handleSubmit,
    },
    [
      errorEl,

      showName &&
        createElement(
          'label',
          {
            htmlFor: 'name',
            className: 'form__label',
          },
          [
            createElement(
              'span',
              { className: 'form__label__text' },
              nameLabel,
              isNameRequired && createElement('span', { className: 'form__label__text--required' }, ' (required)'),
            ),
            nameEl,
          ],
        ),
      !showName && nameEl,

      showEmail &&
        createElement(
          'label',
          {
            htmlFor: 'email',
            className: 'form__label',
          },
          [
            createElement(
              'span',
              { className: 'form__label__text' },
              emailLabel,
              isEmailRequired && createElement('span', { className: 'form__label__text--required' }, ' (required)'),
            ),
            emailEl,
          ],
        ),
      !showEmail && emailEl,

      createElement(
        'label',
        {
          htmlFor: 'message',
          className: 'form__label',
        },
        [
          createElement(
            'span',
            { className: 'form__label__text' },
            messageLabel,
            createElement('span', { className: 'form__label__text--required' }, ' (required)'),
          ),
          messageEl,
        ],
      ),

      createElement(
        'div',
        {
          className: 'btn-group',
        },
        [submitEl, cancelEl],
      ),
    ],
  );

  return {
    get el() {
      return formEl;
    },
    showError,
    hideError,
  };
}

const XMLNS$1 = 'http://www.w3.org/2000/svg';

/**
 * Sentry Logo
 */
function Logo({ colorScheme }) {
  const createElementNS = (tagName) =>
    WINDOW.document.createElementNS(XMLNS$1, tagName);
  const svg = setAttributesNS(createElementNS('svg'), {
    class: 'sentry-logo',
    width: '32',
    height: '30',
    viewBox: '0 0 72 66',
    fill: 'none',
  });

  const path = setAttributesNS(createElementNS('path'), {
    transform: 'translate(11, 11)',
    d: 'M29,2.26a4.67,4.67,0,0,0-8,0L14.42,13.53A32.21,32.21,0,0,1,32.17,40.19H27.55A27.68,27.68,0,0,0,12.09,17.47L6,28a15.92,15.92,0,0,1,9.23,12.17H4.62A.76.76,0,0,1,4,39.06l2.94-5a10.74,10.74,0,0,0-3.36-1.9l-2.91,5a4.54,4.54,0,0,0,1.69,6.24A4.66,4.66,0,0,0,4.62,44H19.15a19.4,19.4,0,0,0-8-17.31l2.31-4A23.87,23.87,0,0,1,23.76,44H36.07a35.88,35.88,0,0,0-16.41-31.8l4.67-8a.77.77,0,0,1,1.05-.27c.53.29,20.29,34.77,20.66,35.17a.76.76,0,0,1-.68,1.13H40.6q.09,1.91,0,3.81h4.78A4.59,4.59,0,0,0,50,39.43a4.49,4.49,0,0,0-.62-2.28Z',
  });
  svg.append(path);

  const defs = createElementNS('defs');
  const style = createElementNS('style');

  if (colorScheme === 'system') {
    style.textContent = `
    @media (prefers-color-scheme: dark) {
      path: {
        fill: '#fff';
      }
    }
    `;
  }

  style.textContent = `
    path {
      fill: ${colorScheme === 'dark' ? '#fff' : '#362d59'};
    }`;

  defs.append(style);
  svg.append(defs);

  return {
    get el() {
      return svg;
    },
  };
}

/**
 * Feedback dialog component that has the form
 */
function Dialog({
  formTitle,
  showBranding,
  showName,
  showEmail,
  isNameRequired,
  isEmailRequired,
  colorScheme,
  defaultName,
  defaultEmail,
  onClosed,
  onCancel,
  onSubmit,
  ...textLabels
}) {
  let el = null;

  /**
   * Handles when the dialog is clicked. In our case, the dialog is the
   * semi-transparent bg behind the form. We want clicks outside of the form to
   * hide the form.
   */
  function handleDialogClick() {
    close();

    // Only this should trigger `onClose`, we don't want the `close()` method to
    // trigger it, otherwise it can cause cycles.
    onClosed && onClosed();
  }

  /**
   * Close the dialog
   */
  function close() {
    if (el) {
      el.open = false;
    }
  }

  /**
   * Opens the dialog
   */
  function open() {
    if (el) {
      el.open = true;
    }
  }

  /**
   * Check if dialog is currently opened
   */
  function checkIsOpen() {
    return (el && el.open === true) || false;
  }

  const {
    el: formEl,
    showError,
    hideError,
  } = Form({
    showEmail,
    showName,
    isEmailRequired,
    isNameRequired,

    defaultName,
    defaultEmail,
    onSubmit,
    onCancel,
    ...textLabels,
  });

  el = createElement(
    'dialog',
    {
      className: 'dialog',
      open: true,
      onClick: handleDialogClick,
    },
    createElement(
      'div',
      {
        className: 'dialog__content',
        onClick: e => {
          // Stop event propagation so clicks on content modal do not propagate to dialog (which will close dialog)
          e.stopPropagation();
        },
      },
      createElement(
        'h2',
        { className: 'dialog__header' },
        formTitle,
        showBranding &&
          createElement(
            'a',
            {
              className: 'brand-link',
              target: '_blank',
              href: 'https://sentry.io/welcome/',
              title: 'Powered by Sentry',
              rel: 'noopener noreferrer',
            },
            Logo({ colorScheme }).el,
          ),
      ),
      formEl,
    ),
  );

  return {
    get el() {
      return el;
    },
    showError,
    hideError,
    open,
    close,
    checkIsOpen,
  };
}

const WIDTH = 16;
const HEIGHT = 17;
const XMLNS = 'http://www.w3.org/2000/svg';

/**
 * Success Icon (checkmark)
 */
function SuccessIcon() {
  const createElementNS = (tagName) =>
    WINDOW.document.createElementNS(XMLNS, tagName);
  const svg = setAttributesNS(createElementNS('svg'), {
    class: 'success-icon',
    width: `${WIDTH}`,
    height: `${HEIGHT}`,
    viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
    fill: 'none',
  });

  const g = setAttributesNS(createElementNS('g'), {
    clipPath: 'url(#clip0_57_156)',
  });

  const path2 = setAttributesNS(createElementNS('path'), {
    ['fill-rule']: 'evenodd',
    ['clip-rule']: 'evenodd',
    d: 'M3.55544 15.1518C4.87103 16.0308 6.41775 16.5 8 16.5C10.1217 16.5 12.1566 15.6571 13.6569 14.1569C15.1571 12.6566 16 10.6217 16 8.5C16 6.91775 15.5308 5.37103 14.6518 4.05544C13.7727 2.73985 12.5233 1.71447 11.0615 1.10897C9.59966 0.503466 7.99113 0.34504 6.43928 0.653721C4.88743 0.962403 3.46197 1.72433 2.34315 2.84315C1.22433 3.96197 0.462403 5.38743 0.153721 6.93928C-0.15496 8.49113 0.00346625 10.0997 0.608967 11.5615C1.21447 13.0233 2.23985 14.2727 3.55544 15.1518ZM4.40546 3.1204C5.46945 2.40946 6.72036 2.03 8 2.03C9.71595 2.03 11.3616 2.71166 12.575 3.92502C13.7883 5.13838 14.47 6.78405 14.47 8.5C14.47 9.77965 14.0905 11.0306 13.3796 12.0945C12.6687 13.1585 11.6582 13.9878 10.476 14.4775C9.29373 14.9672 7.99283 15.0953 6.73777 14.8457C5.48271 14.596 4.32987 13.9798 3.42502 13.075C2.52018 12.1701 1.90397 11.0173 1.65432 9.76224C1.40468 8.50718 1.5328 7.20628 2.0225 6.02404C2.5122 4.8418 3.34148 3.83133 4.40546 3.1204Z',
  });
  const path = setAttributesNS(createElementNS('path'), {
    d: 'M6.68775 12.4297C6.78586 12.4745 6.89218 12.4984 7 12.5C7.11275 12.4955 7.22315 12.4664 7.32337 12.4145C7.4236 12.3627 7.51121 12.2894 7.58 12.2L12 5.63999C12.0848 5.47724 12.1071 5.28902 12.0625 5.11098C12.0178 4.93294 11.9095 4.77744 11.7579 4.67392C11.6064 4.57041 11.4221 4.52608 11.24 4.54931C11.0579 4.57254 10.8907 4.66173 10.77 4.79999L6.88 10.57L5.13 8.56999C5.06508 8.49566 4.98613 8.43488 4.89768 8.39111C4.80922 8.34735 4.713 8.32148 4.61453 8.31498C4.51605 8.30847 4.41727 8.32147 4.32382 8.35322C4.23038 8.38497 4.14413 8.43484 4.07 8.49999C3.92511 8.63217 3.83692 8.81523 3.82387 9.01092C3.81083 9.2066 3.87393 9.39976 4 9.54999L6.43 12.24C6.50187 12.3204 6.58964 12.385 6.68775 12.4297Z',
  });

  svg.appendChild(g).append(path, path2);

  const speakerDefs = createElementNS('defs');
  const speakerClipPathDef = setAttributesNS(createElementNS('clipPath'), {
    id: 'clip0_57_156',
  });

  const speakerRect = setAttributesNS(createElementNS('rect'), {
    width: `${WIDTH}`,
    height: `${WIDTH}`,
    fill: 'white',
    transform: 'translate(0 0.5)',
  });

  speakerClipPathDef.appendChild(speakerRect);
  speakerDefs.appendChild(speakerClipPathDef);

  svg.appendChild(speakerDefs).appendChild(speakerClipPathDef).appendChild(speakerRect);

  return {
    get el() {
      return svg;
    },
  };
}

/**
 * Feedback dialog component that has the form
 */
function SuccessMessage({ message, onRemove }) {
  function remove() {
    if (!el) {
      return;
    }

    el.remove();
    onRemove && onRemove();
  }

  const el = createElement(
    'div',
    {
      className: 'success-message',
      onClick: remove,
    },
    SuccessIcon().el,
    message,
  );

  return {
    el,
    remove,
  };
}

/**
 * Creates a new widget. Returns public methods that control widget behavior.
 */
function createWidget({
  shadow,
  options: { shouldCreateActor = true, ...options },
  attachTo,
}) {
  let actor;
  let dialog;
  let isDialogOpen = false;

  /**
   * Show the success message for 5 seconds
   */
  function showSuccessMessage() {
    if (!shadow) {
      return;
    }

    try {
      const success = SuccessMessage({
        message: options.successMessageText,
        onRemove: () => {
          if (timeoutId) {
            clearTimeout(timeoutId);
          }
          showActor();
        },
      });

      if (!success.el) {
        throw new Error('Unable to show success message');
      }

      shadow.appendChild(success.el);

      const timeoutId = setTimeout(() => {
        if (success) {
          success.remove();
        }
      }, 5000);
    } catch (err) {
      // TODO: error handling
      utils.logger.error(err);
    }
  }

  /**
   * Handler for when the feedback form is completed by the user. This will
   * create and send the feedback message as an event.
   */
  async function _handleFeedbackSubmit(feedback) {
    if (!dialog) {
      return;
    }

    // Simple validation for now, just check for non-empty required fields
    const emptyField = [];
    if (options.isNameRequired && !feedback.name) {
      emptyField.push(options.nameLabel);
    }
    if (options.isEmailRequired && !feedback.email) {
      emptyField.push(options.emailLabel);
    }
    if (!feedback.message) {
      emptyField.push(options.messageLabel);
    }
    if (emptyField.length > 0) {
      dialog.showError(`Please enter in the following required fields: ${emptyField.join(', ')}`);
      return;
    }

    const result = await handleFeedbackSubmit(dialog, feedback);

    // Error submitting feedback
    if (!result) {
      if (options.onSubmitError) {
        options.onSubmitError();
      }

      return;
    }

    // Success
    removeDialog();
    showSuccessMessage();

    if (options.onSubmitSuccess) {
      options.onSubmitSuccess();
    }
  }

  /**
   * Displays the default actor
   */
  function showActor() {
    actor && actor.show();
  }

  /**
   * Hides the default actor
   */
  function hideActor() {
    actor && actor.hide();
  }

  /**
   * Removes the default actor element
   */
  function removeActor() {
    actor && actor.el && actor.el.remove();
  }

  /**
   *
   */
  function openDialog() {
    try {
      if (dialog) {
        dialog.open();
        isDialogOpen = true;
        if (options.onFormOpen) {
          options.onFormOpen();
        }
        return;
      }

      const userKey = options.useSentryUser;
      const scope = core.getCurrentHub().getScope();
      const user = scope && scope.getUser();

      dialog = Dialog({
        colorScheme: options.colorScheme,
        showBranding: options.showBranding,
        showName: options.showName || options.isNameRequired,
        showEmail: options.showEmail || options.isEmailRequired,
        isNameRequired: options.isNameRequired,
        isEmailRequired: options.isEmailRequired,
        formTitle: options.formTitle,
        cancelButtonLabel: options.cancelButtonLabel,
        submitButtonLabel: options.submitButtonLabel,
        emailLabel: options.emailLabel,
        emailPlaceholder: options.emailPlaceholder,
        messageLabel: options.messageLabel,
        messagePlaceholder: options.messagePlaceholder,
        nameLabel: options.nameLabel,
        namePlaceholder: options.namePlaceholder,
        defaultName: (userKey && user && user[userKey.name]) || '',
        defaultEmail: (userKey && user && user[userKey.email]) || '',
        onClosed: () => {
          showActor();
          isDialogOpen = false;

          if (options.onFormClose) {
            options.onFormClose();
          }
        },
        onCancel: () => {
          closeDialog();
          showActor();
        },
        onSubmit: _handleFeedbackSubmit,
      });

      if (!dialog.el) {
        throw new Error('Unable to open Feedback dialog');
      }

      shadow.appendChild(dialog.el);

      // Hides the default actor whenever dialog is opened
      hideActor();

      if (options.onFormOpen) {
        options.onFormOpen();
      }
    } catch (err) {
      // TODO: Error handling?
      utils.logger.error(err);
    }
  }

  /**
   * Closes the dialog
   */
  function closeDialog() {
    if (dialog) {
      dialog.close();
      isDialogOpen = false;

      if (options.onFormClose) {
        options.onFormClose();
      }
    }
  }

  /**
   * Removes the dialog element from DOM
   */
  function removeDialog() {
    if (dialog) {
      closeDialog();
      const dialogEl = dialog.el;
      dialogEl && dialogEl.remove();
      dialog = undefined;
    }
  }

  /**
   *
   */
  function handleActorClick() {
    // Open dialog
    if (!isDialogOpen) {
      openDialog();
    }

    // Hide actor button
    hideActor();
  }

  if (attachTo) {
    attachTo.addEventListener('click', handleActorClick);
  } else if (shouldCreateActor) {
    actor = Actor({ buttonLabel: options.buttonLabel, onClick: handleActorClick });
    actor.el && shadow.appendChild(actor.el);
  }

  return {
    get actor() {
      return actor;
    },
    get dialog() {
      return dialog;
    },

    showActor,
    hideActor,
    removeActor,

    openDialog,
    closeDialog,
    removeDialog,
  };
}

const doc = WINDOW.document;

/**
 * Feedback integration. When added as an integration to the SDK, it will
 * inject a button in the bottom-right corner of the window that opens a
 * feedback modal when clicked.
 */
class Feedback  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Feedback';}

  /**
   * @inheritDoc
   */

  /**
   * Feedback configuration options
   */

  /**
   * Reference to widget element that is created when autoInject is true
   */

  /**
   * List of all widgets that are created from the integration
   */

  /**
   * Reference to the host element where widget is inserted
   */

  /**
   * Refernce to Shadow DOM root
   */

  /**
   * Tracks if actor styles have ever been inserted into shadow DOM
   */

   constructor({
    id = 'sentry-feedback',
    showBranding = true,
    autoInject = true,
    showEmail = true,
    showName = true,
    useSentryUser = {
      email: 'email',
      name: 'username',
    },
    isEmailRequired = false,
    isNameRequired = false,

    themeDark,
    themeLight,
    colorScheme = 'system',

    buttonLabel = ACTOR_LABEL,
    cancelButtonLabel = CANCEL_BUTTON_LABEL,
    submitButtonLabel = SUBMIT_BUTTON_LABEL,
    formTitle = FORM_TITLE,
    emailPlaceholder = EMAIL_PLACEHOLDER,
    emailLabel = EMAIL_LABEL,
    messagePlaceholder = MESSAGE_PLACEHOLDER,
    messageLabel = MESSAGE_LABEL,
    namePlaceholder = NAME_PLACEHOLDER,
    nameLabel = NAME_LABEL,
    successMessageText = SUCCESS_MESSAGE_TEXT,

    onFormClose,
    onFormOpen,
    onSubmitError,
    onSubmitSuccess,
  } = {}) {
    // Initializations
    this.name = Feedback.id;

    // tsc fails if these are not initialized explicitly constructor, e.g. can't call `_initialize()`
    this._host = null;
    this._shadow = null;
    this._widget = null;
    this._widgets = new Set();
    this._hasInsertedActorStyles = false;

    this.options = {
      id,
      showBranding,
      autoInject,
      isEmailRequired,
      isNameRequired,
      showEmail,
      showName,
      useSentryUser,

      colorScheme,
      themeDark: {
        ...DEFAULT_THEME.dark,
        ...themeDark,
      },
      themeLight: {
        ...DEFAULT_THEME.light,
        ...themeLight,
      },

      buttonLabel,
      cancelButtonLabel,
      submitButtonLabel,
      formTitle,
      emailLabel,
      emailPlaceholder,
      messageLabel,
      messagePlaceholder,
      nameLabel,
      namePlaceholder,
      successMessageText,

      onFormClose,
      onFormOpen,
      onSubmitError,
      onSubmitSuccess,
    };
  }

  /**
   * Setup and initialize feedback container
   */
   setupOnce() {
    if (!utils.isBrowser()) {
      return;
    }

    try {
      this._cleanupWidgetIfExists();

      const { autoInject } = this.options;

      if (!autoInject) {
        // Nothing to do here
        return;
      }

      this._createWidget(this.options);
    } catch (err) {
      DEBUG_BUILD && utils.logger.error(err);
    }
  }

  /**
   * Allows user to open the dialog box. Creates a new widget if
   * `autoInject` was false, otherwise re-uses the default widget that was
   * created during initialization of the integration.
   */
   openDialog() {
    if (!this._widget) {
      this._createWidget({ ...this.options, shouldCreateActor: false });
    }

    if (!this._widget) {
      return;
    }

    this._widget.openDialog();
  }

  /**
   * Closes the dialog for the default widget, if it exists
   */
   closeDialog() {
    if (!this._widget) {
      // Nothing to do if widget does not exist
      return;
    }

    this._widget.closeDialog();
  }

  /**
   * Adds click listener to attached element to open a feedback dialog
   */
   attachTo(el, optionOverrides) {
    try {
      const options = mergeOptions(this.options, optionOverrides || {});

      return this._ensureShadowHost(options, ({ shadow }) => {
        const targetEl =
          typeof el === 'string' ? doc.querySelector(el) : typeof el.addEventListener === 'function' ? el : null;

        if (!targetEl) {
          DEBUG_BUILD && utils.logger.error('[Feedback] Unable to attach to target element');
          return null;
        }

        const widget = createWidget({ shadow, options, attachTo: targetEl });
        this._widgets.add(widget);

        if (!this._widget) {
          this._widget = widget;
        }

        return widget;
      });
    } catch (err) {
      DEBUG_BUILD && utils.logger.error(err);
      return null;
    }
  }

  /**
   * Creates a new widget. Accepts partial options to override any options passed to constructor.
   */
   createWidget(
    optionOverrides,
  ) {
    try {
      return this._createWidget(mergeOptions(this.options, optionOverrides || {}));
    } catch (err) {
      DEBUG_BUILD && utils.logger.error(err);
      return null;
    }
  }

  /**
   * Removes a single widget
   */
   removeWidget(widget) {
    if (!widget) {
      return false;
    }

    try {
      if (this._widgets.has(widget)) {
        widget.removeActor();
        widget.removeDialog();
        this._widgets.delete(widget);

        if (this._widget === widget) {
          // TODO: is more clean-up needed? e.g. call remove()
          this._widget = null;
        }

        return true;
      }
    } catch (err) {
      DEBUG_BUILD && utils.logger.error(err);
    }

    return false;
  }

  /**
   * Returns the default (first-created) widget
   */
   getWidget() {
    return this._widget;
  }

  /**
   * Removes the Feedback integration (including host, shadow DOM, and all widgets)
   */
   remove() {
    if (this._host) {
      this._host.remove();
    }
    this._initialize();
  }

  /**
   * Initializes values of protected properties
   */
   _initialize() {
    this._host = null;
    this._shadow = null;
    this._widget = null;
    this._widgets = new Set();
    this._hasInsertedActorStyles = false;
  }

  /**
   * Clean-up the widget if it already exists in the DOM. This shouldn't happen
   * in prod, but can happen in development with hot module reloading.
   */
   _cleanupWidgetIfExists() {
    if (this._host) {
      this.remove();
    }
    const existingFeedback = doc.querySelector(`#${this.options.id}`);
    if (existingFeedback) {
      existingFeedback.remove();
    }
  }

  /**
   * Creates a new widget, after ensuring shadow DOM exists
   */
   _createWidget(options) {
    return this._ensureShadowHost(options, ({ shadow }) => {
      const widget = createWidget({ shadow, options });

      if (!this._hasInsertedActorStyles && widget.actor) {
        shadow.appendChild(createActorStyles(doc));
        this._hasInsertedActorStyles = true;
      }

      this._widgets.add(widget);

      if (!this._widget) {
        this._widget = widget;
      }

      return widget;
    });
  }

  /**
   * Ensures that shadow DOM exists and is added to the DOM
   */
   _ensureShadowHost(
    options,
    cb,
  ) {
    let needsAppendHost = false;

    // Don't create if it already exists
    if (!this._shadow || !this._host) {
      const { id, colorScheme, themeLight, themeDark } = options;
      const { shadow, host } = createShadowHost({
        id,
        colorScheme,
        themeLight,
        themeDark,
      });
      this._shadow = shadow;
      this._host = host;
      needsAppendHost = true;
    }

    // set data attribute on host for different themes
    this._host.dataset.sentryFeedbackColorscheme = options.colorScheme;

    const result = cb({ shadow: this._shadow, host: this._host });

    if (needsAppendHost) {
      doc.body.appendChild(this._host);
    }

    return result;
  }
} Feedback.__initStatic();

exports.Feedback = Feedback;
exports.sendFeedback = sendFeedback;


},{"@sentry/core":65,"@sentry/utils":117}],2:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('../common/debug-build.js');
const types = require('./types.js');

/**
 * Add a listener that cancels and finishes a transaction when the global
 * document is hidden.
 */
function registerBackgroundTabDetection() {
  if (types.WINDOW && types.WINDOW.document) {
    types.WINDOW.document.addEventListener('visibilitychange', () => {
      const activeTransaction = core.getActiveTransaction() ;
      if (types.WINDOW.document.hidden && activeTransaction) {
        const statusType = 'cancelled';

        debugBuild.DEBUG_BUILD &&
          utils.logger.log(
            `[Tracing] Transaction: ${statusType} -> since tab moved to the background, op: ${activeTransaction.op}`,
          );
        // We should not set status if it is already set, this prevent important statuses like
        // error or data loss from being overwritten on transaction.
        if (!activeTransaction.status) {
          activeTransaction.setStatus(statusType);
        }
        activeTransaction.setTag('visibilitychange', 'document.hidden');
        activeTransaction.finish();
      }
    });
  } else {
    debugBuild.DEBUG_BUILD && utils.logger.warn('[Tracing] Could not set up background tab detection due to lack of global document');
  }
}

exports.registerBackgroundTabDetection = registerBackgroundTabDetection;


},{"../common/debug-build.js":21,"./types.js":9,"@sentry/core":65,"@sentry/utils":117}],3:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('../common/debug-build.js');
const backgroundtab = require('./backgroundtab.js');
const index = require('./metrics/index.js');
const request = require('./request.js');
const router = require('./router.js');
const types = require('./types.js');

const BROWSER_TRACING_INTEGRATION_ID = 'BrowserTracing';

/** Options for Browser Tracing integration */

const DEFAULT_BROWSER_TRACING_OPTIONS = {
  ...core.TRACING_DEFAULTS,
  markBackgroundTransactions: true,
  routingInstrumentation: router.instrumentRoutingWithDefaults,
  startTransactionOnLocationChange: true,
  startTransactionOnPageLoad: true,
  enableLongTask: true,
  _experiments: {},
  ...request.defaultRequestInstrumentationOptions,
};

/**
 * The Browser Tracing integration automatically instruments browser pageload/navigation
 * actions as transactions, and captures requests, metrics and errors as spans.
 *
 * The integration can be configured with a variety of options, and can be extended to use
 * any routing library. This integration uses {@see IdleTransaction} to create transactions.
 */
class BrowserTracing  {
  // This class currently doesn't have a static `id` field like the other integration classes, because it prevented
  // @sentry/tracing from being treeshaken. Tree shakers do not like static fields, because they behave like side effects.
  // TODO: Come up with a better plan, than using static fields on integration classes, and use that plan on all
  // integrations.

  /** Browser Tracing integration options */

  /**
   * @inheritDoc
   */

   constructor(_options) {
    this.name = BROWSER_TRACING_INTEGRATION_ID;
    this._hasSetTracePropagationTargets = false;

    core.addTracingExtensions();

    if (debugBuild.DEBUG_BUILD) {
      this._hasSetTracePropagationTargets = !!(
        _options &&
        // eslint-disable-next-line deprecation/deprecation
        (_options.tracePropagationTargets || _options.tracingOrigins)
      );
    }

    this.options = {
      ...DEFAULT_BROWSER_TRACING_OPTIONS,
      ..._options,
    };

    // Special case: enableLongTask can be set in _experiments
    // TODO (v8): Remove this in v8
    if (this.options._experiments.enableLongTask !== undefined) {
      this.options.enableLongTask = this.options._experiments.enableLongTask;
    }

    // TODO (v8): remove this block after tracingOrigins is removed
    // Set tracePropagationTargets to tracingOrigins if specified by the user
    // In case both are specified, tracePropagationTargets takes precedence
    // eslint-disable-next-line deprecation/deprecation
    if (_options && !_options.tracePropagationTargets && _options.tracingOrigins) {
      // eslint-disable-next-line deprecation/deprecation
      this.options.tracePropagationTargets = _options.tracingOrigins;
    }

    this._collectWebVitals = index.startTrackingWebVitals();
    if (this.options.enableLongTask) {
      index.startTrackingLongTasks();
    }
    if (this.options._experiments.enableInteractions) {
      index.startTrackingInteractions();
    }
  }

  /**
   * @inheritDoc
   */
   setupOnce(_, getCurrentHub) {
    this._getCurrentHub = getCurrentHub;
    const hub = getCurrentHub();
    const client = hub.getClient();
    const clientOptions = client && client.getOptions();

    const {
      routingInstrumentation: instrumentRouting,
      startTransactionOnLocationChange,
      startTransactionOnPageLoad,
      markBackgroundTransactions,
      traceFetch,
      traceXHR,
      shouldCreateSpanForRequest,
      enableHTTPTimings,
      _experiments,
    } = this.options;

    const clientOptionsTracePropagationTargets = clientOptions && clientOptions.tracePropagationTargets;
    // There are three ways to configure tracePropagationTargets:
    // 1. via top level client option `tracePropagationTargets`
    // 2. via BrowserTracing option `tracePropagationTargets`
    // 3. via BrowserTracing option `tracingOrigins` (deprecated)
    //
    // To avoid confusion, favour top level client option `tracePropagationTargets`, and fallback to
    // BrowserTracing option `tracePropagationTargets` and then `tracingOrigins` (deprecated).
    // This is done as it minimizes bundle size (we don't have to have undefined checks).
    //
    // If both 1 and either one of 2 or 3 are set (from above), we log out a warning.
    // eslint-disable-next-line deprecation/deprecation
    const tracePropagationTargets = clientOptionsTracePropagationTargets || this.options.tracePropagationTargets;
    if (debugBuild.DEBUG_BUILD && this._hasSetTracePropagationTargets && clientOptionsTracePropagationTargets) {
      utils.logger.warn(
        '[Tracing] The `tracePropagationTargets` option was set in the BrowserTracing integration and top level `Sentry.init`. The top level `Sentry.init` value is being used.',
      );
    }

    instrumentRouting(
      (context) => {
        const transaction = this._createRouteTransaction(context);

        this.options._experiments.onStartRouteTransaction &&
          this.options._experiments.onStartRouteTransaction(transaction, context, getCurrentHub);

        return transaction;
      },
      startTransactionOnPageLoad,
      startTransactionOnLocationChange,
    );

    if (markBackgroundTransactions) {
      backgroundtab.registerBackgroundTabDetection();
    }

    if (_experiments.enableInteractions) {
      this._registerInteractionListener();
    }

    request.instrumentOutgoingRequests({
      traceFetch,
      traceXHR,
      tracePropagationTargets,
      shouldCreateSpanForRequest,
      enableHTTPTimings,
    });
  }

  /** Create routing idle transaction. */
   _createRouteTransaction(context) {
    if (!this._getCurrentHub) {
      debugBuild.DEBUG_BUILD &&
        utils.logger.warn(`[Tracing] Did not create ${context.op} transaction because _getCurrentHub is invalid.`);
      return undefined;
    }

    const hub = this._getCurrentHub();

    const { beforeNavigate, idleTimeout, finalTimeout, heartbeatInterval } = this.options;

    const isPageloadTransaction = context.op === 'pageload';

    const sentryTrace = isPageloadTransaction ? getMetaContent('sentry-trace') : '';
    const baggage = isPageloadTransaction ? getMetaContent('baggage') : '';
    const { traceparentData, dynamicSamplingContext, propagationContext } = utils.tracingContextFromHeaders(
      sentryTrace,
      baggage,
    );

    const expandedContext = {
      ...context,
      ...traceparentData,
      metadata: {
        ...context.metadata,
        dynamicSamplingContext: traceparentData && !dynamicSamplingContext ? {} : dynamicSamplingContext,
      },
      trimEnd: true,
    };

    const modifiedContext = typeof beforeNavigate === 'function' ? beforeNavigate(expandedContext) : expandedContext;

    // For backwards compatibility reasons, beforeNavigate can return undefined to "drop" the transaction (prevent it
    // from being sent to Sentry).
    const finalContext = modifiedContext === undefined ? { ...expandedContext, sampled: false } : modifiedContext;

    // If `beforeNavigate` set a custom name, record that fact
    finalContext.metadata =
      finalContext.name !== expandedContext.name
        ? { ...finalContext.metadata, source: 'custom' }
        : finalContext.metadata;

    this._latestRouteName = finalContext.name;
    this._latestRouteSource = finalContext.metadata && finalContext.metadata.source;

    if (finalContext.sampled === false) {
      debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] Will not send ${finalContext.op} transaction because of beforeNavigate.`);
    }

    debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] Starting ${finalContext.op} transaction on scope`);

    const { location } = types.WINDOW;

    const idleTransaction = core.startIdleTransaction(
      hub,
      finalContext,
      idleTimeout,
      finalTimeout,
      true,
      { location }, // for use in the tracesSampler
      heartbeatInterval,
    );

    const scope = hub.getScope();

    // If it's a pageload and there is a meta tag set
    // use the traceparentData as the propagation context
    if (isPageloadTransaction && traceparentData) {
      scope.setPropagationContext(propagationContext);
    } else {
      // Navigation transactions should set a new propagation context based on the
      // created idle transaction.
      scope.setPropagationContext({
        traceId: idleTransaction.traceId,
        spanId: idleTransaction.spanId,
        parentSpanId: idleTransaction.parentSpanId,
        sampled: idleTransaction.sampled,
      });
    }

    idleTransaction.registerBeforeFinishCallback(transaction => {
      this._collectWebVitals();
      index.addPerformanceEntries(transaction);
    });

    return idleTransaction ;
  }

  /** Start listener for interaction transactions */
   _registerInteractionListener() {
    let inflightInteractionTransaction;
    const registerInteractionTransaction = () => {
      const { idleTimeout, finalTimeout, heartbeatInterval } = this.options;
      const op = 'ui.action.click';

      const currentTransaction = core.getActiveTransaction();
      if (currentTransaction && currentTransaction.op && ['navigation', 'pageload'].includes(currentTransaction.op)) {
        debugBuild.DEBUG_BUILD &&
          utils.logger.warn(
            `[Tracing] Did not create ${op} transaction because a pageload or navigation transaction is in progress.`,
          );
        return undefined;
      }

      if (inflightInteractionTransaction) {
        inflightInteractionTransaction.setFinishReason('interactionInterrupted');
        inflightInteractionTransaction.finish();
        inflightInteractionTransaction = undefined;
      }

      if (!this._getCurrentHub) {
        debugBuild.DEBUG_BUILD && utils.logger.warn(`[Tracing] Did not create ${op} transaction because _getCurrentHub is invalid.`);
        return undefined;
      }

      if (!this._latestRouteName) {
        debugBuild.DEBUG_BUILD && utils.logger.warn(`[Tracing] Did not create ${op} transaction because _latestRouteName is missing.`);
        return undefined;
      }

      const hub = this._getCurrentHub();
      const { location } = types.WINDOW;

      const context = {
        name: this._latestRouteName,
        op,
        trimEnd: true,
        metadata: {
          source: this._latestRouteSource || 'url',
        },
      };

      inflightInteractionTransaction = core.startIdleTransaction(
        hub,
        context,
        idleTimeout,
        finalTimeout,
        true,
        { location }, // for use in the tracesSampler
        heartbeatInterval,
      );
    };

    ['click'].forEach(type => {
      addEventListener(type, registerInteractionTransaction, { once: false, capture: true });
    });
  }
}

/** Returns the value of a meta tag */
function getMetaContent(metaName) {
  // Can't specify generic to `getDomElement` because tracing can be used
  // in a variety of environments, have to disable `no-unsafe-member-access`
  // as a result.
  const metaTag = utils.getDomElement(`meta[name=${metaName}]`);
  // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
  return metaTag ? metaTag.getAttribute('content') : undefined;
}

exports.BROWSER_TRACING_INTEGRATION_ID = BROWSER_TRACING_INTEGRATION_ID;
exports.BrowserTracing = BrowserTracing;
exports.getMetaContent = getMetaContent;


},{"../common/debug-build.js":21,"./backgroundtab.js":2,"./metrics/index.js":5,"./request.js":7,"./router.js":8,"./types.js":9,"@sentry/core":65,"@sentry/utils":117}],4:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../common/debug-build.js');
const getCLS = require('./web-vitals/getCLS.js');
const getFID = require('./web-vitals/getFID.js');
const getLCP = require('./web-vitals/getLCP.js');
const observe = require('./web-vitals/lib/observe.js');

const handlers = {};
const instrumented = {};

let _previousCls;
let _previousFid;
let _previousLcp;

/**
 * Add a callback that will be triggered when a CLS metric is available.
 * Returns a cleanup callback which can be called to remove the instrumentation handler.
 */
function addClsInstrumentationHandler(callback) {
  return addMetricObserver('cls', callback, instrumentCls, _previousCls);
}

/**
 * Add a callback that will be triggered when a LCP metric is available.
 * Returns a cleanup callback which can be called to remove the instrumentation handler.
 */
function addLcpInstrumentationHandler(callback) {
  return addMetricObserver('lcp', callback, instrumentLcp, _previousLcp);
}

/**
 * Add a callback that will be triggered when a FID metric is available.
 * Returns a cleanup callback which can be called to remove the instrumentation handler.
 */
function addFidInstrumentationHandler(callback) {
  return addMetricObserver('fid', callback, instrumentFid, _previousFid);
}

/**
 * Add a callback that will be triggered when a performance observer is triggered,
 * and receives the entries of the observer.
 * Returns a cleanup callback which can be called to remove the instrumentation handler.
 */
function addPerformanceInstrumentationHandler(
  type,
  callback,
) {
  addHandler(type, callback);

  if (!instrumented[type]) {
    instrumentPerformanceObserver(type);
    instrumented[type] = true;
  }

  return getCleanupCallback(type, callback);
}

/** Trigger all handlers of a given type. */
function triggerHandlers(type, data) {
  const typeHandlers = handlers[type];

  if (!typeHandlers || !typeHandlers.length) {
    return;
  }

  for (const handler of typeHandlers) {
    try {
      handler(data);
    } catch (e) {
      debugBuild.DEBUG_BUILD &&
        utils.logger.error(
          `Error while triggering instrumentation handler.\nType: ${type}\nName: ${utils.getFunctionName(handler)}\nError:`,
          e,
        );
    }
  }
}

function instrumentCls() {
  getCLS.onCLS(metric => {
    triggerHandlers('cls', {
      metric,
    });
    _previousCls = metric;
  });
}

function instrumentFid() {
  getFID.onFID(metric => {
    triggerHandlers('fid', {
      metric,
    });
    _previousFid = metric;
  });
}

function instrumentLcp() {
  getLCP.onLCP(metric => {
    triggerHandlers('lcp', {
      metric,
    });
    _previousLcp = metric;
  });
}

function addMetricObserver(
  type,
  callback,
  instrumentFn,
  previousValue,
) {
  addHandler(type, callback);

  if (!instrumented[type]) {
    instrumentFn();
    instrumented[type] = true;
  }

  if (previousValue) {
    callback({ metric: previousValue });
  }

  return getCleanupCallback(type, callback);
}

function instrumentPerformanceObserver(type) {
  const options = {};

  // Special per-type options we want to use
  if (type === 'event') {
    options.durationThreshold = 0;
  }

  observe.observe(
    type,
    entries => {
      triggerHandlers(type, { entries });
    },
    options,
  );
}

function addHandler(type, handler) {
  handlers[type] = handlers[type] || [];
  (handlers[type] ).push(handler);
}

// Get a callback which can be called to remove the instrumentation handler
function getCleanupCallback(type, callback) {
  return () => {
    const typeHandlers = handlers[type];

    if (!typeHandlers) {
      return;
    }

    const index = typeHandlers.indexOf(callback);
    if (index !== -1) {
      typeHandlers.splice(index, 1);
    }
  };
}

exports.addClsInstrumentationHandler = addClsInstrumentationHandler;
exports.addFidInstrumentationHandler = addFidInstrumentationHandler;
exports.addLcpInstrumentationHandler = addLcpInstrumentationHandler;
exports.addPerformanceInstrumentationHandler = addPerformanceInstrumentationHandler;


},{"../common/debug-build.js":21,"./web-vitals/getCLS.js":10,"./web-vitals/getFID.js":11,"./web-vitals/getLCP.js":12,"./web-vitals/lib/observe.js":19,"@sentry/utils":117}],5:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const instrument = require('../instrument.js');
const types = require('../types.js');
const getVisibilityWatcher = require('../web-vitals/lib/getVisibilityWatcher.js');
const utils$1 = require('./utils.js');

const MAX_INT_AS_BYTES = 2147483647;

/**
 * Converts from milliseconds to seconds
 * @param time time in ms
 */
function msToSec(time) {
  return time / 1000;
}

function getBrowserPerformanceAPI() {
  // @ts-expect-error we want to make sure all of these are available, even if TS is sure they are
  return types.WINDOW && types.WINDOW.addEventListener && types.WINDOW.performance;
}

let _performanceCursor = 0;

let _measurements = {};
let _lcpEntry;
let _clsEntry;

/**
 * Start tracking web vitals
 *
 * @returns A function that forces web vitals collection
 */
function startTrackingWebVitals() {
  const performance = getBrowserPerformanceAPI();
  if (performance && utils.browserPerformanceTimeOrigin) {
    // @ts-expect-error we want to make sure all of these are available, even if TS is sure they are
    if (performance.mark) {
      types.WINDOW.performance.mark('sentry-tracing-init');
    }
    const fidCallback = _trackFID();
    const clsCallback = _trackCLS();
    const lcpCallback = _trackLCP();

    return () => {
      fidCallback();
      clsCallback();
      lcpCallback();
    };
  }

  return () => undefined;
}

/**
 * Start tracking long tasks.
 */
function startTrackingLongTasks() {
  instrument.addPerformanceInstrumentationHandler('longtask', ({ entries }) => {
    for (const entry of entries) {
      const transaction = core.getActiveTransaction() ;
      if (!transaction) {
        return;
      }
      const startTime = msToSec((utils.browserPerformanceTimeOrigin ) + entry.startTime);
      const duration = msToSec(entry.duration);

      transaction.startChild({
        description: 'Main UI thread blocked',
        op: 'ui.long-task',
        origin: 'auto.ui.browser.metrics',
        startTimestamp: startTime,
        endTimestamp: startTime + duration,
      });
    }
  });
}

/**
 * Start tracking interaction events.
 */
function startTrackingInteractions() {
  instrument.addPerformanceInstrumentationHandler('event', ({ entries }) => {
    for (const entry of entries) {
      const transaction = core.getActiveTransaction() ;
      if (!transaction) {
        return;
      }

      if (entry.name === 'click') {
        const startTime = msToSec((utils.browserPerformanceTimeOrigin ) + entry.startTime);
        const duration = msToSec(entry.duration);

        transaction.startChild({
          description: utils.htmlTreeAsString(entry.target),
          op: `ui.interaction.${entry.name}`,
          origin: 'auto.ui.browser.metrics',
          startTimestamp: startTime,
          endTimestamp: startTime + duration,
        });
      }
    }
  });
}

/** Starts tracking the Cumulative Layout Shift on the current page. */
function _trackCLS() {
  return instrument.addClsInstrumentationHandler(({ metric }) => {
    const entry = metric.entries.pop();
    if (!entry) {
      return;
    }

    debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding CLS');
    _measurements['cls'] = { value: metric.value, unit: '' };
    _clsEntry = entry ;
  });
}

/** Starts tracking the Largest Contentful Paint on the current page. */
function _trackLCP() {
  return instrument.addLcpInstrumentationHandler(({ metric }) => {
    const entry = metric.entries.pop();
    if (!entry) {
      return;
    }

    debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding LCP');
    _measurements['lcp'] = { value: metric.value, unit: 'millisecond' };
    _lcpEntry = entry ;
  });
}

/** Starts tracking the First Input Delay on the current page. */
function _trackFID() {
  return instrument.addFidInstrumentationHandler(({ metric }) => {
    const entry = metric.entries.pop();
    if (!entry) {
      return;
    }

    const timeOrigin = msToSec(utils.browserPerformanceTimeOrigin );
    const startTime = msToSec(entry.startTime);
    debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding FID');
    _measurements['fid'] = { value: metric.value, unit: 'millisecond' };
    _measurements['mark.fid'] = { value: timeOrigin + startTime, unit: 'second' };
  });
}

/** Add performance related spans to a transaction */
function addPerformanceEntries(transaction) {
  const performance = getBrowserPerformanceAPI();
  if (!performance || !types.WINDOW.performance.getEntries || !utils.browserPerformanceTimeOrigin) {
    // Gatekeeper if performance API not available
    return;
  }

  debugBuild.DEBUG_BUILD && utils.logger.log('[Tracing] Adding & adjusting spans using Performance API');
  const timeOrigin = msToSec(utils.browserPerformanceTimeOrigin);

  const performanceEntries = performance.getEntries();

  let responseStartTimestamp;
  let requestStartTimestamp;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  performanceEntries.slice(_performanceCursor).forEach((entry) => {
    const startTime = msToSec(entry.startTime);
    const duration = msToSec(entry.duration);

    if (transaction.op === 'navigation' && timeOrigin + startTime < transaction.startTimestamp) {
      return;
    }

    switch (entry.entryType) {
      case 'navigation': {
        _addNavigationSpans(transaction, entry, timeOrigin);
        responseStartTimestamp = timeOrigin + msToSec(entry.responseStart);
        requestStartTimestamp = timeOrigin + msToSec(entry.requestStart);
        break;
      }
      case 'mark':
      case 'paint':
      case 'measure': {
        _addMeasureSpans(transaction, entry, startTime, duration, timeOrigin);

        // capture web vitals
        const firstHidden = getVisibilityWatcher.getVisibilityWatcher();
        // Only report if the page wasn't hidden prior to the web vital.
        const shouldRecord = entry.startTime < firstHidden.firstHiddenTime;

        if (entry.name === 'first-paint' && shouldRecord) {
          debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding FP');
          _measurements['fp'] = { value: entry.startTime, unit: 'millisecond' };
        }
        if (entry.name === 'first-contentful-paint' && shouldRecord) {
          debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding FCP');
          _measurements['fcp'] = { value: entry.startTime, unit: 'millisecond' };
        }
        break;
      }
      case 'resource': {
        const resourceName = (entry.name ).replace(types.WINDOW.location.origin, '');
        _addResourceSpans(transaction, entry, resourceName, startTime, duration, timeOrigin);
        break;
      }
      // Ignore other entry types.
    }
  });

  _performanceCursor = Math.max(performanceEntries.length - 1, 0);

  _trackNavigator(transaction);

  // Measurements are only available for pageload transactions
  if (transaction.op === 'pageload') {
    // Generate TTFB (Time to First Byte), which measured as the time between the beginning of the transaction and the
    // start of the response in milliseconds
    if (typeof responseStartTimestamp === 'number') {
      debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding TTFB');
      _measurements['ttfb'] = {
        value: (responseStartTimestamp - transaction.startTimestamp) * 1000,
        unit: 'millisecond',
      };

      if (typeof requestStartTimestamp === 'number' && requestStartTimestamp <= responseStartTimestamp) {
        // Capture the time spent making the request and receiving the first byte of the response.
        // This is the time between the start of the request and the start of the response in milliseconds.
        _measurements['ttfb.requestTime'] = {
          value: (responseStartTimestamp - requestStartTimestamp) * 1000,
          unit: 'millisecond',
        };
      }
    }

    ['fcp', 'fp', 'lcp'].forEach(name => {
      if (!_measurements[name] || timeOrigin >= transaction.startTimestamp) {
        return;
      }
      // The web vitals, fcp, fp, lcp, and ttfb, all measure relative to timeOrigin.
      // Unfortunately, timeOrigin is not captured within the transaction span data, so these web vitals will need
      // to be adjusted to be relative to transaction.startTimestamp.
      const oldValue = _measurements[name].value;
      const measurementTimestamp = timeOrigin + msToSec(oldValue);

      // normalizedValue should be in milliseconds
      const normalizedValue = Math.abs((measurementTimestamp - transaction.startTimestamp) * 1000);
      const delta = normalizedValue - oldValue;

      debugBuild.DEBUG_BUILD && utils.logger.log(`[Measurements] Normalized ${name} from ${oldValue} to ${normalizedValue} (${delta})`);
      _measurements[name].value = normalizedValue;
    });

    const fidMark = _measurements['mark.fid'];
    if (fidMark && _measurements['fid']) {
      // create span for FID
      utils$1._startChild(transaction, {
        description: 'first input delay',
        endTimestamp: fidMark.value + msToSec(_measurements['fid'].value),
        op: 'ui.action',
        origin: 'auto.ui.browser.metrics',
        startTimestamp: fidMark.value,
      });

      // Delete mark.fid as we don't want it to be part of final payload
      delete _measurements['mark.fid'];
    }

    // If FCP is not recorded we should not record the cls value
    // according to the new definition of CLS.
    if (!('fcp' in _measurements)) {
      delete _measurements.cls;
    }

    Object.keys(_measurements).forEach(measurementName => {
      transaction.setMeasurement(
        measurementName,
        _measurements[measurementName].value,
        _measurements[measurementName].unit,
      );
    });

    _tagMetricInfo(transaction);
  }

  _lcpEntry = undefined;
  _clsEntry = undefined;
  _measurements = {};
}

/** Create measure related spans */
function _addMeasureSpans(
  transaction,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  entry,
  startTime,
  duration,
  timeOrigin,
) {
  const measureStartTimestamp = timeOrigin + startTime;
  const measureEndTimestamp = measureStartTimestamp + duration;

  utils$1._startChild(transaction, {
    description: entry.name ,
    endTimestamp: measureEndTimestamp,
    op: entry.entryType ,
    origin: 'auto.resource.browser.metrics',
    startTimestamp: measureStartTimestamp,
  });

  return measureStartTimestamp;
}

/** Instrument navigation entries */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _addNavigationSpans(transaction, entry, timeOrigin) {
  ['unloadEvent', 'redirect', 'domContentLoadedEvent', 'loadEvent', 'connect'].forEach(event => {
    _addPerformanceNavigationTiming(transaction, entry, event, timeOrigin);
  });
  _addPerformanceNavigationTiming(transaction, entry, 'secureConnection', timeOrigin, 'TLS/SSL', 'connectEnd');
  _addPerformanceNavigationTiming(transaction, entry, 'fetch', timeOrigin, 'cache', 'domainLookupStart');
  _addPerformanceNavigationTiming(transaction, entry, 'domainLookup', timeOrigin, 'DNS');
  _addRequest(transaction, entry, timeOrigin);
}

/** Create performance navigation related spans */
function _addPerformanceNavigationTiming(
  transaction,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  entry,
  event,
  timeOrigin,
  description,
  eventEnd,
) {
  const end = eventEnd ? (entry[eventEnd] ) : (entry[`${event}End`] );
  const start = entry[`${event}Start`] ;
  if (!start || !end) {
    return;
  }
  utils$1._startChild(transaction, {
    op: 'browser',
    origin: 'auto.browser.browser.metrics',
    description: description || event,
    startTimestamp: timeOrigin + msToSec(start),
    endTimestamp: timeOrigin + msToSec(end),
  });
}

/** Create request and response related spans */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _addRequest(transaction, entry, timeOrigin) {
  utils$1._startChild(transaction, {
    op: 'browser',
    origin: 'auto.browser.browser.metrics',
    description: 'request',
    startTimestamp: timeOrigin + msToSec(entry.requestStart ),
    endTimestamp: timeOrigin + msToSec(entry.responseEnd ),
  });

  utils$1._startChild(transaction, {
    op: 'browser',
    origin: 'auto.browser.browser.metrics',
    description: 'response',
    startTimestamp: timeOrigin + msToSec(entry.responseStart ),
    endTimestamp: timeOrigin + msToSec(entry.responseEnd ),
  });
}

/** Create resource-related spans */
function _addResourceSpans(
  transaction,
  entry,
  resourceName,
  startTime,
  duration,
  timeOrigin,
) {
  // we already instrument based on fetch and xhr, so we don't need to
  // duplicate spans here.
  if (entry.initiatorType === 'xmlhttprequest' || entry.initiatorType === 'fetch') {
    return;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = {};
  setResourceEntrySizeData(data, entry, 'transferSize', 'http.response_transfer_size');
  setResourceEntrySizeData(data, entry, 'encodedBodySize', 'http.response_content_length');
  setResourceEntrySizeData(data, entry, 'decodedBodySize', 'http.decoded_response_content_length');
  if ('renderBlockingStatus' in entry) {
    data['resource.render_blocking_status'] = entry.renderBlockingStatus;
  }

  const startTimestamp = timeOrigin + startTime;
  const endTimestamp = startTimestamp + duration;

  utils$1._startChild(transaction, {
    description: resourceName,
    endTimestamp,
    op: entry.initiatorType ? `resource.${entry.initiatorType}` : 'resource.other',
    origin: 'auto.resource.browser.metrics',
    startTimestamp,
    data,
  });
}

/**
 * Capture the information of the user agent.
 */
function _trackNavigator(transaction) {
  const navigator = types.WINDOW.navigator ;
  if (!navigator) {
    return;
  }

  // track network connectivity
  const connection = navigator.connection;
  if (connection) {
    if (connection.effectiveType) {
      transaction.setTag('effectiveConnectionType', connection.effectiveType);
    }

    if (connection.type) {
      transaction.setTag('connectionType', connection.type);
    }

    if (utils$1.isMeasurementValue(connection.rtt)) {
      _measurements['connection.rtt'] = { value: connection.rtt, unit: 'millisecond' };
    }
  }

  if (utils$1.isMeasurementValue(navigator.deviceMemory)) {
    transaction.setTag('deviceMemory', `${navigator.deviceMemory} GB`);
  }

  if (utils$1.isMeasurementValue(navigator.hardwareConcurrency)) {
    transaction.setTag('hardwareConcurrency', String(navigator.hardwareConcurrency));
  }
}

/** Add LCP / CLS data to transaction to allow debugging */
function _tagMetricInfo(transaction) {
  if (_lcpEntry) {
    debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding LCP Data');

    // Capture Properties of the LCP element that contributes to the LCP.

    if (_lcpEntry.element) {
      transaction.setTag('lcp.element', utils.htmlTreeAsString(_lcpEntry.element));
    }

    if (_lcpEntry.id) {
      transaction.setTag('lcp.id', _lcpEntry.id);
    }

    if (_lcpEntry.url) {
      // Trim URL to the first 200 characters.
      transaction.setTag('lcp.url', _lcpEntry.url.trim().slice(0, 200));
    }

    transaction.setTag('lcp.size', _lcpEntry.size);
  }

  // See: https://developer.mozilla.org/en-US/docs/Web/API/LayoutShift
  if (_clsEntry && _clsEntry.sources) {
    debugBuild.DEBUG_BUILD && utils.logger.log('[Measurements] Adding CLS Data');
    _clsEntry.sources.forEach((source, index) =>
      transaction.setTag(`cls.source.${index + 1}`, utils.htmlTreeAsString(source.node)),
    );
  }
}

function setResourceEntrySizeData(
  data,
  entry,
  key,
  dataKey,
) {
  const entryVal = entry[key];
  if (entryVal != null && entryVal < MAX_INT_AS_BYTES) {
    data[dataKey] = entryVal;
  }
}

exports._addMeasureSpans = _addMeasureSpans;
exports._addResourceSpans = _addResourceSpans;
exports.addPerformanceEntries = addPerformanceEntries;
exports.startTrackingInteractions = startTrackingInteractions;
exports.startTrackingLongTasks = startTrackingLongTasks;
exports.startTrackingWebVitals = startTrackingWebVitals;


},{"../../common/debug-build.js":21,"../instrument.js":4,"../types.js":9,"../web-vitals/lib/getVisibilityWatcher.js":17,"./utils.js":6,"@sentry/core":65,"@sentry/utils":117}],6:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Checks if a given value is a valid measurement value.
 */
function isMeasurementValue(value) {
  return typeof value === 'number' && isFinite(value);
}

/**
 * Helper function to start child on transactions. This function will make sure that the transaction will
 * use the start timestamp of the created child span if it is earlier than the transactions actual
 * start timestamp.
 */
function _startChild(transaction, { startTimestamp, ...ctx }) {
  if (startTimestamp && transaction.startTimestamp > startTimestamp) {
    transaction.startTimestamp = startTimestamp;
  }

  return transaction.startChild({
    startTimestamp,
    ...ctx,
  });
}

exports._startChild = _startChild;
exports.isMeasurementValue = isMeasurementValue;


},{}],7:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const fetch = require('../common/fetch.js');
const instrument = require('./instrument.js');

/* eslint-disable max-lines */

const DEFAULT_TRACE_PROPAGATION_TARGETS = ['localhost', /^\/(?!\/)/];

/** Options for Request Instrumentation */

const defaultRequestInstrumentationOptions = {
  traceFetch: true,
  traceXHR: true,
  enableHTTPTimings: true,
  // TODO (v8): Remove this property
  tracingOrigins: DEFAULT_TRACE_PROPAGATION_TARGETS,
  tracePropagationTargets: DEFAULT_TRACE_PROPAGATION_TARGETS,
};

/** Registers span creators for xhr and fetch requests  */
function instrumentOutgoingRequests(_options) {
  const {
    traceFetch,
    traceXHR,
    // eslint-disable-next-line deprecation/deprecation
    tracePropagationTargets,
    // eslint-disable-next-line deprecation/deprecation
    tracingOrigins,
    shouldCreateSpanForRequest,
    enableHTTPTimings,
  } = {
    traceFetch: defaultRequestInstrumentationOptions.traceFetch,
    traceXHR: defaultRequestInstrumentationOptions.traceXHR,
    ..._options,
  };

  const shouldCreateSpan =
    typeof shouldCreateSpanForRequest === 'function' ? shouldCreateSpanForRequest : (_) => true;

  // TODO(v8) Remove tracingOrigins here
  // The only reason we're passing it in here is because this instrumentOutgoingRequests function is publicly exported
  // and we don't want to break the API. We can remove it in v8.
  const shouldAttachHeadersWithTargets = (url) =>
    shouldAttachHeaders(url, tracePropagationTargets || tracingOrigins);

  const spans = {};

  if (traceFetch) {
    utils.addFetchInstrumentationHandler(handlerData => {
      const createdSpan = fetch.instrumentFetchRequest(handlerData, shouldCreateSpan, shouldAttachHeadersWithTargets, spans);
      if (enableHTTPTimings && createdSpan) {
        addHTTPTimings(createdSpan);
      }
    });
  }

  if (traceXHR) {
    utils.addXhrInstrumentationHandler(handlerData => {
      const createdSpan = xhrCallback(handlerData, shouldCreateSpan, shouldAttachHeadersWithTargets, spans);
      if (enableHTTPTimings && createdSpan) {
        addHTTPTimings(createdSpan);
      }
    });
  }
}

function isPerformanceResourceTiming(entry) {
  return (
    entry.entryType === 'resource' &&
    'initiatorType' in entry &&
    typeof (entry ).nextHopProtocol === 'string' &&
    (entry.initiatorType === 'fetch' || entry.initiatorType === 'xmlhttprequest')
  );
}

/**
 * Creates a temporary observer to listen to the next fetch/xhr resourcing timings,
 * so that when timings hit their per-browser limit they don't need to be removed.
 *
 * @param span A span that has yet to be finished, must contain `url` on data.
 */
function addHTTPTimings(span) {
  const url = span.data.url;

  if (!url) {
    return;
  }

  const cleanup = instrument.addPerformanceInstrumentationHandler('resource', ({ entries }) => {
    entries.forEach(entry => {
      if (isPerformanceResourceTiming(entry) && entry.name.endsWith(url)) {
        const spanData = resourceTimingEntryToSpanData(entry);
        spanData.forEach(data => span.setData(...data));
        // In the next tick, clean this handler up
        // We have to wait here because otherwise this cleans itself up before it is fully done
        setTimeout(cleanup);
      }
    });
  });
}

/**
 * Converts ALPN protocol ids to name and version.
 *
 * (https://www.iana.org/assignments/tls-extensiontype-values/tls-extensiontype-values.xhtml#alpn-protocol-ids)
 * @param nextHopProtocol PerformanceResourceTiming.nextHopProtocol
 */
function extractNetworkProtocol(nextHopProtocol) {
  let name = 'unknown';
  let version = 'unknown';
  let _name = '';
  for (const char of nextHopProtocol) {
    // http/1.1 etc.
    if (char === '/') {
      [name, version] = nextHopProtocol.split('/');
      break;
    }
    // h2, h3 etc.
    if (!isNaN(Number(char))) {
      name = _name === 'h' ? 'http' : _name;
      version = nextHopProtocol.split(_name)[1];
      break;
    }
    _name += char;
  }
  if (_name === nextHopProtocol) {
    // webrtc, ftp, etc.
    name = _name;
  }
  return { name, version };
}

function getAbsoluteTime(time = 0) {
  return ((utils.browserPerformanceTimeOrigin || performance.timeOrigin) + time) / 1000;
}

function resourceTimingEntryToSpanData(resourceTiming) {
  const { name, version } = extractNetworkProtocol(resourceTiming.nextHopProtocol);

  const timingSpanData = [];

  timingSpanData.push(['network.protocol.version', version], ['network.protocol.name', name]);

  if (!utils.browserPerformanceTimeOrigin) {
    return timingSpanData;
  }
  return [
    ...timingSpanData,
    ['http.request.redirect_start', getAbsoluteTime(resourceTiming.redirectStart)],
    ['http.request.fetch_start', getAbsoluteTime(resourceTiming.fetchStart)],
    ['http.request.domain_lookup_start', getAbsoluteTime(resourceTiming.domainLookupStart)],
    ['http.request.domain_lookup_end', getAbsoluteTime(resourceTiming.domainLookupEnd)],
    ['http.request.connect_start', getAbsoluteTime(resourceTiming.connectStart)],
    ['http.request.secure_connection_start', getAbsoluteTime(resourceTiming.secureConnectionStart)],
    ['http.request.connection_end', getAbsoluteTime(resourceTiming.connectEnd)],
    ['http.request.request_start', getAbsoluteTime(resourceTiming.requestStart)],
    ['http.request.response_start', getAbsoluteTime(resourceTiming.responseStart)],
    ['http.request.response_end', getAbsoluteTime(resourceTiming.responseEnd)],
  ];
}

/**
 * A function that determines whether to attach tracing headers to a request.
 * This was extracted from `instrumentOutgoingRequests` to make it easier to test shouldAttachHeaders.
 * We only export this fuction for testing purposes.
 */
function shouldAttachHeaders(url, tracePropagationTargets) {
  return utils.stringMatchesSomePattern(url, tracePropagationTargets || DEFAULT_TRACE_PROPAGATION_TARGETS);
}

/**
 * Create and track xhr request spans
 *
 * @returns Span if a span was created, otherwise void.
 */
// eslint-disable-next-line complexity
function xhrCallback(
  handlerData,
  shouldCreateSpan,
  shouldAttachHeaders,
  spans,
) {
  const xhr = handlerData.xhr;
  const sentryXhrData = xhr && xhr[utils.SENTRY_XHR_DATA_KEY];

  if (!core.hasTracingEnabled() || !xhr || xhr.__sentry_own_request__ || !sentryXhrData) {
    return undefined;
  }

  const shouldCreateSpanResult = shouldCreateSpan(sentryXhrData.url);

  // check first if the request has finished and is tracked by an existing span which should now end
  if (handlerData.endTimestamp && shouldCreateSpanResult) {
    const spanId = xhr.__sentry_xhr_span_id__;
    if (!spanId) return;

    const span = spans[spanId];
    if (span && sentryXhrData.status_code !== undefined) {
      span.setHttpStatus(sentryXhrData.status_code);
      span.finish();

      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
      delete spans[spanId];
    }
    return undefined;
  }

  const hub = core.getCurrentHub();
  const scope = hub.getScope();
  const parentSpan = scope.getSpan();

  const span =
    shouldCreateSpanResult && parentSpan
      ? parentSpan.startChild({
          data: {
            type: 'xhr',
            'http.method': sentryXhrData.method,
            url: sentryXhrData.url,
          },
          description: `${sentryXhrData.method} ${sentryXhrData.url}`,
          op: 'http.client',
          origin: 'auto.http.browser',
        })
      : undefined;

  if (span) {
    xhr.__sentry_xhr_span_id__ = span.spanId;
    spans[xhr.__sentry_xhr_span_id__] = span;
  }

  if (xhr.setRequestHeader && shouldAttachHeaders(sentryXhrData.url)) {
    if (span) {
      const transaction = span && span.transaction;
      const dynamicSamplingContext = transaction && transaction.getDynamicSamplingContext();
      const sentryBaggageHeader = utils.dynamicSamplingContextToSentryBaggageHeader(dynamicSamplingContext);
      setHeaderOnXhr(xhr, span.toTraceparent(), sentryBaggageHeader);
    } else {
      const client = hub.getClient();
      const { traceId, sampled, dsc } = scope.getPropagationContext();
      const sentryTraceHeader = utils.generateSentryTraceHeader(traceId, undefined, sampled);
      const dynamicSamplingContext =
        dsc || (client ? core.getDynamicSamplingContextFromClient(traceId, client, scope) : undefined);
      const sentryBaggageHeader = utils.dynamicSamplingContextToSentryBaggageHeader(dynamicSamplingContext);
      setHeaderOnXhr(xhr, sentryTraceHeader, sentryBaggageHeader);
    }
  }

  return span;
}

function setHeaderOnXhr(
  xhr,
  sentryTraceHeader,
  sentryBaggageHeader,
) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    xhr.setRequestHeader('sentry-trace', sentryTraceHeader);
    if (sentryBaggageHeader) {
      // From MDN: "If this method is called several times with the same header, the values are merged into one single request header."
      // We can therefore simply set a baggage header without checking what was there before
      // https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/setRequestHeader
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      xhr.setRequestHeader(utils.BAGGAGE_HEADER_NAME, sentryBaggageHeader);
    }
  } catch (_) {
    // Error: InvalidStateError: Failed to execute 'setRequestHeader' on 'XMLHttpRequest': The object's state must be OPENED.
  }
}

exports.DEFAULT_TRACE_PROPAGATION_TARGETS = DEFAULT_TRACE_PROPAGATION_TARGETS;
exports.defaultRequestInstrumentationOptions = defaultRequestInstrumentationOptions;
exports.extractNetworkProtocol = extractNetworkProtocol;
exports.instrumentOutgoingRequests = instrumentOutgoingRequests;
exports.shouldAttachHeaders = shouldAttachHeaders;
exports.xhrCallback = xhrCallback;


},{"../common/fetch.js":22,"./instrument.js":4,"@sentry/core":65,"@sentry/utils":117}],8:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../common/debug-build.js');
const types = require('./types.js');

/**
 * Default function implementing pageload and navigation transactions
 */
function instrumentRoutingWithDefaults(
  customStartTransaction,
  startTransactionOnPageLoad = true,
  startTransactionOnLocationChange = true,
) {
  if (!types.WINDOW || !types.WINDOW.location) {
    debugBuild.DEBUG_BUILD && utils.logger.warn('Could not initialize routing instrumentation due to invalid location');
    return;
  }

  let startingUrl = types.WINDOW.location.href;

  let activeTransaction;
  if (startTransactionOnPageLoad) {
    activeTransaction = customStartTransaction({
      name: types.WINDOW.location.pathname,
      // pageload should always start at timeOrigin (and needs to be in s, not ms)
      startTimestamp: utils.browserPerformanceTimeOrigin ? utils.browserPerformanceTimeOrigin / 1000 : undefined,
      op: 'pageload',
      origin: 'auto.pageload.browser',
      metadata: { source: 'url' },
    });
  }

  if (startTransactionOnLocationChange) {
    utils.addHistoryInstrumentationHandler(({ to, from }) => {
      /**
       * This early return is there to account for some cases where a navigation transaction starts right after
       * long-running pageload. We make sure that if `from` is undefined and a valid `startingURL` exists, we don't
       * create an uneccessary navigation transaction.
       *
       * This was hard to duplicate, but this behavior stopped as soon as this fix was applied. This issue might also
       * only be caused in certain development environments where the usage of a hot module reloader is causing
       * errors.
       */
      if (from === undefined && startingUrl && startingUrl.indexOf(to) !== -1) {
        startingUrl = undefined;
        return;
      }

      if (from !== to) {
        startingUrl = undefined;
        if (activeTransaction) {
          debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] Finishing current transaction with op: ${activeTransaction.op}`);
          // If there's an open transaction on the scope, we need to finish it before creating an new one.
          activeTransaction.finish();
        }
        activeTransaction = customStartTransaction({
          name: types.WINDOW.location.pathname,
          op: 'navigation',
          origin: 'auto.navigation.browser',
          metadata: { source: 'url' },
        });
      }
    });
  }
}

exports.instrumentRoutingWithDefaults = instrumentRoutingWithDefaults;


},{"../common/debug-build.js":21,"./types.js":9,"@sentry/utils":117}],9:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

const WINDOW = utils.GLOBAL_OBJ ;

exports.WINDOW = WINDOW;


},{"@sentry/utils":117}],10:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const bindReporter = require('./lib/bindReporter.js');
const initMetric = require('./lib/initMetric.js');
const observe = require('./lib/observe.js');
const onHidden = require('./lib/onHidden.js');

/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * Calculates the [CLS](https://web.dev/cls/) value for the current page and
 * calls the `callback` function once the value is ready to be reported, along
 * with all `layout-shift` performance entries that were used in the metric
 * value calculation. The reported value is a `double` (corresponding to a
 * [layout shift score](https://web.dev/cls/#layout-shift-score)).
 *
 * If the `reportAllChanges` configuration option is set to `true`, the
 * `callback` function will be called as soon as the value is initially
 * determined as well as any time the value changes throughout the page
 * lifespan.
 *
 * _**Important:** CLS should be continually monitored for changes throughout
 * the entire lifespan of a page—including if the user returns to the page after
 * it's been hidden/backgrounded. However, since browsers often [will not fire
 * additional callbacks once the user has backgrounded a
 * page](https://developer.chrome.com/blog/page-lifecycle-api/#advice-hidden),
 * `callback` is always called when the page's visibility state changes to
 * hidden. As a result, the `callback` function might be called multiple times
 * during the same page load._
 */
const onCLS = (onReport) => {
  const metric = initMetric.initMetric('CLS', 0);
  let report;

  let sessionValue = 0;
  let sessionEntries = [];

  // const handleEntries = (entries: Metric['entries']) => {
  const handleEntries = (entries) => {
    entries.forEach(entry => {
      // Only count layout shifts without recent user input.
      if (!entry.hadRecentInput) {
        const firstSessionEntry = sessionEntries[0];
        const lastSessionEntry = sessionEntries[sessionEntries.length - 1];

        // If the entry occurred less than 1 second after the previous entry and
        // less than 5 seconds after the first entry in the session, include the
        // entry in the current session. Otherwise, start a new session.
        if (
          sessionValue &&
          sessionEntries.length !== 0 &&
          entry.startTime - lastSessionEntry.startTime < 1000 &&
          entry.startTime - firstSessionEntry.startTime < 5000
        ) {
          sessionValue += entry.value;
          sessionEntries.push(entry);
        } else {
          sessionValue = entry.value;
          sessionEntries = [entry];
        }

        // If the current session value is larger than the current CLS value,
        // update CLS and the entries contributing to it.
        if (sessionValue > metric.value) {
          metric.value = sessionValue;
          metric.entries = sessionEntries;
          if (report) {
            report();
          }
        }
      }
    });
  };

  const po = observe.observe('layout-shift', handleEntries);
  if (po) {
    report = bindReporter.bindReporter(onReport, metric);

    const stopListening = () => {
      handleEntries(po.takeRecords() );
      report(true);
    };

    onHidden.onHidden(stopListening);

    return stopListening;
  }

  return;
};

exports.onCLS = onCLS;


},{"./lib/bindReporter.js":13,"./lib/initMetric.js":18,"./lib/observe.js":19,"./lib/onHidden.js":20}],11:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const bindReporter = require('./lib/bindReporter.js');
const getVisibilityWatcher = require('./lib/getVisibilityWatcher.js');
const initMetric = require('./lib/initMetric.js');
const observe = require('./lib/observe.js');
const onHidden = require('./lib/onHidden.js');

/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * Calculates the [FID](https://web.dev/fid/) value for the current page and
 * calls the `callback` function once the value is ready, along with the
 * relevant `first-input` performance entry used to determine the value. The
 * reported value is a `DOMHighResTimeStamp`.
 *
 * _**Important:** since FID is only reported after the user interacts with the
 * page, it's possible that it will not be reported for some page loads._
 */
const onFID = (onReport) => {
  const visibilityWatcher = getVisibilityWatcher.getVisibilityWatcher();
  const metric = initMetric.initMetric('FID');
  // eslint-disable-next-line prefer-const
  let report;

  const handleEntry = (entry) => {
    // Only report if the page wasn't hidden prior to the first input.
    if (entry.startTime < visibilityWatcher.firstHiddenTime) {
      metric.value = entry.processingStart - entry.startTime;
      metric.entries.push(entry);
      report(true);
    }
  };

  const handleEntries = (entries) => {
    (entries ).forEach(handleEntry);
  };

  const po = observe.observe('first-input', handleEntries);
  report = bindReporter.bindReporter(onReport, metric);

  if (po) {
    onHidden.onHidden(() => {
      handleEntries(po.takeRecords() );
      po.disconnect();
    }, true);
  }
};

exports.onFID = onFID;


},{"./lib/bindReporter.js":13,"./lib/getVisibilityWatcher.js":17,"./lib/initMetric.js":18,"./lib/observe.js":19,"./lib/onHidden.js":20}],12:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const bindReporter = require('./lib/bindReporter.js');
const getActivationStart = require('./lib/getActivationStart.js');
const getVisibilityWatcher = require('./lib/getVisibilityWatcher.js');
const initMetric = require('./lib/initMetric.js');
const observe = require('./lib/observe.js');
const onHidden = require('./lib/onHidden.js');

/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const reportedMetricIDs = {};

/**
 * Calculates the [LCP](https://web.dev/lcp/) value for the current page and
 * calls the `callback` function once the value is ready (along with the
 * relevant `largest-contentful-paint` performance entry used to determine the
 * value). The reported value is a `DOMHighResTimeStamp`.
 */
const onLCP = (onReport) => {
  const visibilityWatcher = getVisibilityWatcher.getVisibilityWatcher();
  const metric = initMetric.initMetric('LCP');
  let report;

  const handleEntries = (entries) => {
    const lastEntry = entries[entries.length - 1] ;
    if (lastEntry) {
      // The startTime attribute returns the value of the renderTime if it is
      // not 0, and the value of the loadTime otherwise. The activationStart
      // reference is used because LCP should be relative to page activation
      // rather than navigation start if the page was prerendered.
      const value = Math.max(lastEntry.startTime - getActivationStart.getActivationStart(), 0);

      // Only report if the page wasn't hidden prior to LCP.
      if (value < visibilityWatcher.firstHiddenTime) {
        metric.value = value;
        metric.entries = [lastEntry];
        report();
      }
    }
  };

  const po = observe.observe('largest-contentful-paint', handleEntries);

  if (po) {
    report = bindReporter.bindReporter(onReport, metric);

    const stopListening = () => {
      if (!reportedMetricIDs[metric.id]) {
        handleEntries(po.takeRecords() );
        po.disconnect();
        reportedMetricIDs[metric.id] = true;
        report(true);
      }
    };

    // Stop listening after input. Note: while scrolling is an input that
    // stop LCP observation, it's unreliable since it can be programmatically
    // generated. See: https://github.com/GoogleChrome/web-vitals/issues/75
    ['keydown', 'click'].forEach(type => {
      addEventListener(type, stopListening, { once: true, capture: true });
    });

    onHidden.onHidden(stopListening, true);

    return stopListening;
  }

  return;
};

exports.onLCP = onLCP;


},{"./lib/bindReporter.js":13,"./lib/getActivationStart.js":15,"./lib/getVisibilityWatcher.js":17,"./lib/initMetric.js":18,"./lib/observe.js":19,"./lib/onHidden.js":20}],13:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const bindReporter = (
  callback,
  metric,
  reportAllChanges,
) => {
  let prevValue;
  let delta;
  return (forceReport) => {
    if (metric.value >= 0) {
      if (forceReport || reportAllChanges) {
        delta = metric.value - (prevValue || 0);

        // Report the metric if there's a non-zero delta or if no previous
        // value exists (which can happen in the case of the document becoming
        // hidden when the metric value is 0).
        // See: https://github.com/GoogleChrome/web-vitals/issues/14
        if (delta || prevValue === undefined) {
          prevValue = metric.value;
          metric.delta = delta;
          callback(metric);
        }
      }
    }
  };
};

exports.bindReporter = bindReporter;


},{}],14:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * Performantly generate a unique, 30-char string by combining a version
 * number, the current timestamp with a 13-digit number integer.
 * @return {string}
 */
const generateUniqueID = () => {
  return `v3-${Date.now()}-${Math.floor(Math.random() * (9e12 - 1)) + 1e12}`;
};

exports.generateUniqueID = generateUniqueID;


},{}],15:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const getNavigationEntry = require('./getNavigationEntry.js');

/*
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const getActivationStart = () => {
  const navEntry = getNavigationEntry.getNavigationEntry();
  return (navEntry && navEntry.activationStart) || 0;
};

exports.getActivationStart = getActivationStart;


},{"./getNavigationEntry.js":16}],16:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const types = require('../../types.js');

/*
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const getNavigationEntryFromPerformanceTiming = () => {
  // eslint-disable-next-line deprecation/deprecation
  const timing = types.WINDOW.performance.timing;
  // eslint-disable-next-line deprecation/deprecation
  const type = types.WINDOW.performance.navigation.type;

  const navigationEntry = {
    entryType: 'navigation',
    startTime: 0,
    type: type == 2 ? 'back_forward' : type === 1 ? 'reload' : 'navigate',
  };

  for (const key in timing) {
    if (key !== 'navigationStart' && key !== 'toJSON') {
      // eslint-disable-next-line deprecation/deprecation
      navigationEntry[key] = Math.max((timing[key ] ) - timing.navigationStart, 0);
    }
  }
  return navigationEntry ;
};

const getNavigationEntry = () => {
  if (types.WINDOW.__WEB_VITALS_POLYFILL__) {
    return (
      types.WINDOW.performance &&
      ((performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) ||
        getNavigationEntryFromPerformanceTiming())
    );
  } else {
    return types.WINDOW.performance && performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
  }
};

exports.getNavigationEntry = getNavigationEntry;


},{"../../types.js":9}],17:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const types = require('../../types.js');
const onHidden = require('./onHidden.js');

/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

let firstHiddenTime = -1;

const initHiddenTime = () => {
  // If the document is hidden and not prerendering, assume it was always
  // hidden and the page was loaded in the background.
  return types.WINDOW.document.visibilityState === 'hidden' && !types.WINDOW.document.prerendering ? 0 : Infinity;
};

const trackChanges = () => {
  // Update the time if/when the document becomes hidden.
  onHidden.onHidden(({ timeStamp }) => {
    firstHiddenTime = timeStamp;
  }, true);
};

const getVisibilityWatcher = (

) => {
  if (firstHiddenTime < 0) {
    // If the document is hidden when this code runs, assume it was hidden
    // since navigation start. This isn't a perfect heuristic, but it's the
    // best we can do until an API is available to support querying past
    // visibilityState.
    firstHiddenTime = initHiddenTime();
    trackChanges();
  }
  return {
    get firstHiddenTime() {
      return firstHiddenTime;
    },
  };
};

exports.getVisibilityWatcher = getVisibilityWatcher;


},{"../../types.js":9,"./onHidden.js":20}],18:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const types = require('../../types.js');
const generateUniqueID = require('./generateUniqueID.js');
const getActivationStart = require('./getActivationStart.js');
const getNavigationEntry = require('./getNavigationEntry.js');

/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const initMetric = (name, value) => {
  const navEntry = getNavigationEntry.getNavigationEntry();
  let navigationType = 'navigate';

  if (navEntry) {
    if (types.WINDOW.document.prerendering || getActivationStart.getActivationStart() > 0) {
      navigationType = 'prerender';
    } else {
      navigationType = navEntry.type.replace(/_/g, '-') ;
    }
  }

  return {
    name,
    value: typeof value === 'undefined' ? -1 : value,
    rating: 'good', // Will be updated if the value changes.
    delta: 0,
    entries: [],
    id: generateUniqueID.generateUniqueID(),
    navigationType,
  };
};

exports.initMetric = initMetric;


},{"../../types.js":9,"./generateUniqueID.js":14,"./getActivationStart.js":15,"./getNavigationEntry.js":16}],19:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Takes a performance entry type and a callback function, and creates a
 * `PerformanceObserver` instance that will observe the specified entry type
 * with buffering enabled and call the callback _for each entry_.
 *
 * This function also feature-detects entry support and wraps the logic in a
 * try/catch to avoid errors in unsupporting browsers.
 */
const observe = (
  type,
  callback,
  opts,
) => {
  try {
    if (PerformanceObserver.supportedEntryTypes.includes(type)) {
      const po = new PerformanceObserver(list => {
        callback(list.getEntries() );
      });
      po.observe(
        Object.assign(
          {
            type,
            buffered: true,
          },
          opts || {},
        ) ,
      );
      return po;
    }
  } catch (e) {
    // Do nothing.
  }
  return;
};

exports.observe = observe;


},{}],20:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const types = require('../../types.js');

/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const onHidden = (cb, once) => {
  const onHiddenOrPageHide = (event) => {
    if (event.type === 'pagehide' || types.WINDOW.document.visibilityState === 'hidden') {
      cb(event);
      if (once) {
        removeEventListener('visibilitychange', onHiddenOrPageHide, true);
        removeEventListener('pagehide', onHiddenOrPageHide, true);
      }
    }
  };
  addEventListener('visibilitychange', onHiddenOrPageHide, true);
  // Some browsers have buggy implementations of visibilitychange,
  // so we use pagehide in addition, just to be safe.
  addEventListener('pagehide', onHiddenOrPageHide, true);
};

exports.onHidden = onHidden;


},{"../../types.js":9}],21:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * This serves as a build time flag that will be true by default, but false in non-debug builds or if users replace `__SENTRY_DEBUG__` in their generated code.
 *
 * ATTENTION: This constant must never cross package boundaries (i.e. be exported) to guarantee that it can be used for tree shaking.
 */
const DEBUG_BUILD = (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__);

exports.DEBUG_BUILD = DEBUG_BUILD;


},{}],22:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');

/**
 * Create and track fetch request spans for usage in combination with `addInstrumentationHandler`.
 *
 * @returns Span if a span was created, otherwise void.
 */
function instrumentFetchRequest(
  handlerData,
  shouldCreateSpan,
  shouldAttachHeaders,
  spans,
  spanOrigin = 'auto.http.browser',
) {
  if (!core.hasTracingEnabled() || !handlerData.fetchData) {
    return undefined;
  }

  const shouldCreateSpanResult = shouldCreateSpan(handlerData.fetchData.url);

  if (handlerData.endTimestamp && shouldCreateSpanResult) {
    const spanId = handlerData.fetchData.__span;
    if (!spanId) return;

    const span = spans[spanId];
    if (span) {
      if (handlerData.response) {
        span.setHttpStatus(handlerData.response.status);

        const contentLength =
          handlerData.response && handlerData.response.headers && handlerData.response.headers.get('content-length');

        if (contentLength) {
          const contentLengthNum = parseInt(contentLength);
          if (contentLengthNum > 0) {
            span.setData('http.response_content_length', contentLengthNum);
          }
        }
      } else if (handlerData.error) {
        span.setStatus('internal_error');
      }
      span.finish();

      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
      delete spans[spanId];
    }
    return undefined;
  }

  const hub = core.getCurrentHub();
  const scope = hub.getScope();
  const client = hub.getClient();
  const parentSpan = scope.getSpan();

  const { method, url } = handlerData.fetchData;

  const span =
    shouldCreateSpanResult && parentSpan
      ? parentSpan.startChild({
          data: {
            url,
            type: 'fetch',
            'http.method': method,
          },
          description: `${method} ${url}`,
          op: 'http.client',
          origin: spanOrigin,
        })
      : undefined;

  if (span) {
    handlerData.fetchData.__span = span.spanId;
    spans[span.spanId] = span;
  }

  if (shouldAttachHeaders(handlerData.fetchData.url) && client) {
    const request = handlerData.args[0];

    // In case the user hasn't set the second argument of a fetch call we default it to `{}`.
    handlerData.args[1] = handlerData.args[1] || {};

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const options = handlerData.args[1];

    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access
    options.headers = addTracingHeadersToFetchRequest(request, client, scope, options, span);
  }

  return span;
}

/**
 * Adds sentry-trace and baggage headers to the various forms of fetch headers
 */
function addTracingHeadersToFetchRequest(
  request, // unknown is actually type Request but we can't export DOM types from this package,
  client,
  scope,
  options

,
  requestSpan,
) {
  const span = requestSpan || scope.getSpan();

  const transaction = span && span.transaction;

  const { traceId, sampled, dsc } = scope.getPropagationContext();

  const sentryTraceHeader = span ? span.toTraceparent() : utils.generateSentryTraceHeader(traceId, undefined, sampled);
  const dynamicSamplingContext = transaction
    ? transaction.getDynamicSamplingContext()
    : dsc
      ? dsc
      : core.getDynamicSamplingContextFromClient(traceId, client, scope);

  const sentryBaggageHeader = utils.dynamicSamplingContextToSentryBaggageHeader(dynamicSamplingContext);

  const headers =
    typeof Request !== 'undefined' && utils.isInstanceOf(request, Request) ? (request ).headers : options.headers;

  if (!headers) {
    return { 'sentry-trace': sentryTraceHeader, baggage: sentryBaggageHeader };
  } else if (typeof Headers !== 'undefined' && utils.isInstanceOf(headers, Headers)) {
    const newHeaders = new Headers(headers );

    newHeaders.append('sentry-trace', sentryTraceHeader);

    if (sentryBaggageHeader) {
      // If the same header is appended multiple times the browser will merge the values into a single request header.
      // Its therefore safe to simply push a "baggage" entry, even though there might already be another baggage header.
      newHeaders.append(utils.BAGGAGE_HEADER_NAME, sentryBaggageHeader);
    }

    return newHeaders ;
  } else if (Array.isArray(headers)) {
    const newHeaders = [...headers, ['sentry-trace', sentryTraceHeader]];

    if (sentryBaggageHeader) {
      // If there are multiple entries with the same key, the browser will merge the values into a single request header.
      // Its therefore safe to simply push a "baggage" entry, even though there might already be another baggage header.
      newHeaders.push([utils.BAGGAGE_HEADER_NAME, sentryBaggageHeader]);
    }

    return newHeaders ;
  } else {
    const existingBaggageHeader = 'baggage' in headers ? headers.baggage : undefined;
    const newBaggageHeaders = [];

    if (Array.isArray(existingBaggageHeader)) {
      newBaggageHeaders.push(...existingBaggageHeader);
    } else if (existingBaggageHeader) {
      newBaggageHeaders.push(existingBaggageHeader);
    }

    if (sentryBaggageHeader) {
      newBaggageHeaders.push(sentryBaggageHeader);
    }

    return {
      ...(headers ),
      'sentry-trace': sentryTraceHeader,
      baggage: newBaggageHeaders.length > 0 ? newBaggageHeaders.join(',') : undefined,
    };
  }
}

exports.addTracingHeadersToFetchRequest = addTracingHeadersToFetchRequest;
exports.instrumentFetchRequest = instrumentFetchRequest;


},{"@sentry/core":65,"@sentry/utils":117}],23:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');

/**
 * @private
 */
function _autoloadDatabaseIntegrations() {
  const carrier = core.getMainCarrier();
  if (!carrier.__SENTRY__) {
    return;
  }

  const packageToIntegrationMapping = {
    mongodb() {
      const integration = utils.dynamicRequire(module, './node/integrations/mongo')

;
      return new integration.Mongo();
    },
    mongoose() {
      const integration = utils.dynamicRequire(module, './node/integrations/mongo')

;
      return new integration.Mongo();
    },
    mysql() {
      const integration = utils.dynamicRequire(module, './node/integrations/mysql')

;
      return new integration.Mysql();
    },
    pg() {
      const integration = utils.dynamicRequire(module, './node/integrations/postgres')

;
      return new integration.Postgres();
    },
  };

  const mappedPackages = Object.keys(packageToIntegrationMapping)
    .filter(moduleName => !!utils.loadModule(moduleName))
    .map(pkg => {
      try {
        return packageToIntegrationMapping[pkg]();
      } catch (e) {
        return undefined;
      }
    })
    .filter(p => p) ;

  if (mappedPackages.length > 0) {
    carrier.__SENTRY__.integrations = [...(carrier.__SENTRY__.integrations || []), ...mappedPackages];
  }
}

/**
 * This patches the global object and injects the Tracing extensions methods
 */
function addExtensionMethods() {
  core.addTracingExtensions();

  // Detect and automatically load specified integrations.
  if (utils.isNodeEnv()) {
    _autoloadDatabaseIntegrations();
  }
}

exports.addExtensionMethods = addExtensionMethods;


},{"@sentry/core":65,"@sentry/utils":117}],24:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const express = require('./node/integrations/express.js');
const postgres = require('./node/integrations/postgres.js');
const mysql = require('./node/integrations/mysql.js');
const mongo = require('./node/integrations/mongo.js');
const prisma = require('./node/integrations/prisma.js');
const graphql = require('./node/integrations/graphql.js');
const apollo = require('./node/integrations/apollo.js');
const lazy = require('./node/integrations/lazy.js');
const browsertracing = require('./browser/browsertracing.js');
const request = require('./browser/request.js');
const instrument = require('./browser/instrument.js');
const fetch = require('./common/fetch.js');
const extensions = require('./extensions.js');



exports.IdleTransaction = core.IdleTransaction;
exports.Span = core.Span;
exports.SpanStatus = core.SpanStatus;
exports.Transaction = core.Transaction;
exports.extractTraceparentData = core.extractTraceparentData;
exports.getActiveTransaction = core.getActiveTransaction;
exports.hasTracingEnabled = core.hasTracingEnabled;
exports.spanStatusfromHttpCode = core.spanStatusfromHttpCode;
exports.startIdleTransaction = core.startIdleTransaction;
exports.TRACEPARENT_REGEXP = utils.TRACEPARENT_REGEXP;
exports.stripUrlQueryAndFragment = utils.stripUrlQueryAndFragment;
exports.Express = express.Express;
exports.Postgres = postgres.Postgres;
exports.Mysql = mysql.Mysql;
exports.Mongo = mongo.Mongo;
exports.Prisma = prisma.Prisma;
exports.GraphQL = graphql.GraphQL;
exports.Apollo = apollo.Apollo;
exports.lazyLoadedNodePerformanceMonitoringIntegrations = lazy.lazyLoadedNodePerformanceMonitoringIntegrations;
exports.BROWSER_TRACING_INTEGRATION_ID = browsertracing.BROWSER_TRACING_INTEGRATION_ID;
exports.BrowserTracing = browsertracing.BrowserTracing;
exports.defaultRequestInstrumentationOptions = request.defaultRequestInstrumentationOptions;
exports.instrumentOutgoingRequests = request.instrumentOutgoingRequests;
exports.addClsInstrumentationHandler = instrument.addClsInstrumentationHandler;
exports.addFidInstrumentationHandler = instrument.addFidInstrumentationHandler;
exports.addLcpInstrumentationHandler = instrument.addLcpInstrumentationHandler;
exports.addPerformanceInstrumentationHandler = instrument.addPerformanceInstrumentationHandler;
exports.addTracingHeadersToFetchRequest = fetch.addTracingHeadersToFetchRequest;
exports.instrumentFetchRequest = fetch.instrumentFetchRequest;
exports.addExtensionMethods = extensions.addExtensionMethods;


},{"./browser/browsertracing.js":3,"./browser/instrument.js":4,"./browser/request.js":7,"./common/fetch.js":22,"./extensions.js":23,"./node/integrations/apollo.js":25,"./node/integrations/express.js":26,"./node/integrations/graphql.js":27,"./node/integrations/lazy.js":28,"./node/integrations/mongo.js":29,"./node/integrations/mysql.js":30,"./node/integrations/postgres.js":31,"./node/integrations/prisma.js":32,"@sentry/core":65,"@sentry/utils":117}],25:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils');

Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const nodeUtils = require('./utils/node-utils.js');

/** Tracing integration for Apollo */
class Apollo  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Apollo';}

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
   constructor(
    options = {
      useNestjs: false,
    },
  ) {
    this.name = Apollo.id;
    this._useNest = !!options.useNestjs;
  }

  /** @inheritdoc */
   loadDependency() {
    if (this._useNest) {
      this._module = this._module || utils.loadModule('@nestjs/graphql');
    } else {
      this._module = this._module || utils.loadModule('apollo-server-core');
    }

    return this._module;
  }

  /**
   * @inheritDoc
   */
   setupOnce(_, getCurrentHub) {
    if (nodeUtils.shouldDisableAutoInstrumentation(getCurrentHub)) {
      debugBuild.DEBUG_BUILD && utils.logger.log('Apollo Integration is skipped because of instrumenter configuration.');
      return;
    }

    if (this._useNest) {
      const pkg = this.loadDependency();

      if (!pkg) {
        debugBuild.DEBUG_BUILD && utils.logger.error('Apollo-NestJS Integration was unable to require @nestjs/graphql package.');
        return;
      }

      /**
       * Iterate over resolvers of NestJS ResolversExplorerService before schemas are constructed.
       */
      utils.fill(
        pkg.GraphQLFactory.prototype,
        'mergeWithSchema',
        function (orig) {
          return function (

            ...args
          ) {
            utils.fill(this.resolversExplorerService, 'explore', function (orig) {
              return function () {
                const resolvers = utils.arrayify(orig.call(this));

                const instrumentedResolvers = instrumentResolvers(resolvers, getCurrentHub);

                return instrumentedResolvers;
              };
            });

            return orig.call(this, ...args);
          };
        },
      );
    } else {
      const pkg = this.loadDependency();

      if (!pkg) {
        debugBuild.DEBUG_BUILD && utils.logger.error('Apollo Integration was unable to require apollo-server-core package.');
        return;
      }

      /**
       * Iterate over resolvers of the ApolloServer instance before schemas are constructed.
       */
      utils.fill(pkg.ApolloServerBase.prototype, 'constructSchema', function (orig) {
        return function (

) {
          if (!this.config.resolvers) {
            if (debugBuild.DEBUG_BUILD) {
              if (this.config.schema) {
                utils.logger.warn(
                  'Apollo integration is not able to trace `ApolloServer` instances constructed via `schema` property.' +
                    'If you are using NestJS with Apollo, please use `Sentry.Integrations.Apollo({ useNestjs: true })` instead.',
                );
                utils.logger.warn();
              } else if (this.config.modules) {
                utils.logger.warn(
                  'Apollo integration is not able to trace `ApolloServer` instances constructed via `modules` property.',
                );
              }

              utils.logger.error('Skipping tracing as no resolvers found on the `ApolloServer` instance.');
            }

            return orig.call(this);
          }

          const resolvers = utils.arrayify(this.config.resolvers);

          this.config.resolvers = instrumentResolvers(resolvers, getCurrentHub);

          return orig.call(this);
        };
      });
    }
  }
}Apollo.__initStatic();

function instrumentResolvers(resolvers, getCurrentHub) {
  return resolvers.map(model => {
    Object.keys(model).forEach(resolverGroupName => {
      Object.keys(model[resolverGroupName]).forEach(resolverName => {
        if (typeof model[resolverGroupName][resolverName] !== 'function') {
          return;
        }

        wrapResolver(model, resolverGroupName, resolverName, getCurrentHub);
      });
    });

    return model;
  });
}

/**
 * Wrap a single resolver which can be a parent of other resolvers and/or db operations.
 */
function wrapResolver(
  model,
  resolverGroupName,
  resolverName,
  getCurrentHub,
) {
  utils.fill(model[resolverGroupName], resolverName, function (orig) {
    return function ( ...args) {
      const scope = getCurrentHub().getScope();
      const parentSpan = scope.getSpan();
      const span = _optionalChain([parentSpan, 'optionalAccess', _2 => _2.startChild, 'call', _3 => _3({
        description: `${resolverGroupName}.${resolverName}`,
        op: 'graphql.resolve',
        origin: 'auto.graphql.apollo',
      })]);

      const rv = orig.call(this, ...args);

      if (utils.isThenable(rv)) {
        return rv.then((res) => {
          _optionalChain([span, 'optionalAccess', _4 => _4.finish, 'call', _5 => _5()]);
          return res;
        });
      }

      _optionalChain([span, 'optionalAccess', _6 => _6.finish, 'call', _7 => _7()]);

      return rv;
    };
  });
}

exports.Apollo = Apollo;


},{"../../common/debug-build.js":21,"./utils/node-utils.js":33,"@sentry/utils":117}],26:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils');

Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const nodeUtils = require('./utils/node-utils.js');

/**
 * Express integration
 *
 * Provides an request and error handler for Express framework as well as tracing capabilities
 */
class Express  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Express';}

  /**
   * @inheritDoc
   */

  /**
   * Express App instance
   */

  /**
   * @inheritDoc
   */
   constructor(options = {}) {
    this.name = Express.id;
    this._router = options.router || options.app;
    this._methods = (Array.isArray(options.methods) ? options.methods : []).concat('use');
  }

  /**
   * @inheritDoc
   */
   setupOnce(_, getCurrentHub) {
    if (!this._router) {
      debugBuild.DEBUG_BUILD && utils.logger.error('ExpressIntegration is missing an Express instance');
      return;
    }

    if (nodeUtils.shouldDisableAutoInstrumentation(getCurrentHub)) {
      debugBuild.DEBUG_BUILD && utils.logger.log('Express Integration is skipped because of instrumenter configuration.');
      return;
    }

    instrumentMiddlewares(this._router, this._methods);
    instrumentRouter(this._router );
  }
}Express.__initStatic();

/**
 * Wraps original middleware function in a tracing call, which stores the info about the call as a span,
 * and finishes it once the middleware is done invoking.
 *
 * Express middlewares have 3 various forms, thus we have to take care of all of them:
 * // sync
 * app.use(function (req, res) { ... })
 * // async
 * app.use(function (req, res, next) { ... })
 * // error handler
 * app.use(function (err, req, res, next) { ... })
 *
 * They all internally delegate to the `router[method]` of the given application instance.
 */
// eslint-disable-next-line @typescript-eslint/ban-types, @typescript-eslint/no-explicit-any
function wrap(fn, method) {
  const arity = fn.length;

  switch (arity) {
    case 2: {
      return function ( req, res) {
        const transaction = res.__sentry_transaction;
        if (transaction) {
          const span = transaction.startChild({
            description: fn.name,
            op: `middleware.express.${method}`,
            origin: 'auto.middleware.express',
          });
          res.once('finish', () => {
            span.finish();
          });
        }
        return fn.call(this, req, res);
      };
    }
    case 3: {
      return function (

        req,
        res,
        next,
      ) {
        const transaction = res.__sentry_transaction;
        const span = _optionalChain([transaction, 'optionalAccess', _2 => _2.startChild, 'call', _3 => _3({
          description: fn.name,
          op: `middleware.express.${method}`,
          origin: 'auto.middleware.express',
        })]);
        fn.call(this, req, res, function ( ...args) {
          _optionalChain([span, 'optionalAccess', _4 => _4.finish, 'call', _5 => _5()]);
          next.call(this, ...args);
        });
      };
    }
    case 4: {
      return function (

        err,
        req,
        res,
        next,
      ) {
        const transaction = res.__sentry_transaction;
        const span = _optionalChain([transaction, 'optionalAccess', _6 => _6.startChild, 'call', _7 => _7({
          description: fn.name,
          op: `middleware.express.${method}`,
          origin: 'auto.middleware.express',
        })]);
        fn.call(this, err, req, res, function ( ...args) {
          _optionalChain([span, 'optionalAccess', _8 => _8.finish, 'call', _9 => _9()]);
          next.call(this, ...args);
        });
      };
    }
    default: {
      throw new Error(`Express middleware takes 2-4 arguments. Got: ${arity}`);
    }
  }
}

/**
 * Takes all the function arguments passed to the original `app` or `router` method, eg. `app.use` or `router.use`
 * and wraps every function, as well as array of functions with a call to our `wrap` method.
 * We have to take care of the arrays as well as iterate over all of the arguments,
 * as `app.use` can accept middlewares in few various forms.
 *
 * app.use([<path>], <fn>)
 * app.use([<path>], <fn>, ...<fn>)
 * app.use([<path>], ...<fn>[])
 */
function wrapMiddlewareArgs(args, method) {
  return args.map((arg) => {
    if (typeof arg === 'function') {
      return wrap(arg, method);
    }

    if (Array.isArray(arg)) {
      return arg.map((a) => {
        if (typeof a === 'function') {
          return wrap(a, method);
        }
        return a;
      });
    }

    return arg;
  });
}

/**
 * Patches original router to utilize our tracing functionality
 */
function patchMiddleware(router, method) {
  const originalCallback = router[method];

  router[method] = function (...args) {
    return originalCallback.call(this, ...wrapMiddlewareArgs(args, method));
  };

  return router;
}

/**
 * Patches original router methods
 */
function instrumentMiddlewares(router, methods = []) {
  methods.forEach((method) => patchMiddleware(router, method));
}

/**
 * Patches the prototype of Express.Router to accumulate the resolved route
 * if a layer instance's `match` function was called and it returned a successful match.
 *
 * @see https://github.com/expressjs/express/blob/master/lib/router/index.js
 *
 * @param appOrRouter the router instance which can either be an app (i.e. top-level) or a (nested) router.
 */
function instrumentRouter(appOrRouter) {
  // This is how we can distinguish between app and routers
  const isApp = 'settings' in appOrRouter;

  // In case the app's top-level router hasn't been initialized yet, we have to do it now
  if (isApp && appOrRouter._router === undefined && appOrRouter.lazyrouter) {
    appOrRouter.lazyrouter();
  }

  const router = isApp ? appOrRouter._router : appOrRouter;

  if (!router) {
    /*
    If we end up here, this means likely that this integration is used with Express 3 or Express 5.
    For now, we don't support these versions (3 is very old and 5 is still in beta). To support Express 5,
    we'd need to make more changes to the routing instrumentation because the router is no longer part of
    the Express core package but maintained in its own package. The new router has different function
    signatures and works slightly differently, demanding more changes than just taking the router from
    `app.router` instead of `app._router`.
    @see https://github.com/pillarjs/router

    TODO: Proper Express 5 support
    */
    debugBuild.DEBUG_BUILD && utils.logger.debug('Cannot instrument router for URL Parameterization (did not find a valid router).');
    debugBuild.DEBUG_BUILD && utils.logger.debug('Routing instrumentation is currently only supported in Express 4.');
    return;
  }

  const routerProto = Object.getPrototypeOf(router) ;

  const originalProcessParams = routerProto.process_params;
  routerProto.process_params = function process_params(
    layer,
    called,
    req,
    res,
    done,
  ) {
    // Base case: We're in the first part of the URL (thus we start with the root '/')
    if (!req._reconstructedRoute) {
      req._reconstructedRoute = '';
    }

    // If the layer's partial route has params, is a regex or an array, the route is stored in layer.route.
    const { layerRoutePath, isRegex, isArray, numExtraSegments } = getLayerRoutePathInfo(layer);

    if (layerRoutePath || isRegex || isArray) {
      req._hasParameters = true;
    }

    // Otherwise, the hardcoded path (i.e. a partial route without params) is stored in layer.path
    let partialRoute;

    if (layerRoutePath) {
      partialRoute = layerRoutePath;
    } else {
      /**
       * prevent duplicate segment in _reconstructedRoute param if router match multiple routes before final path
       * example:
       * original url: /api/v1/1234
       * prevent: /api/api/v1/:userId
       * router structure
       * /api -> middleware
       * /api/v1 -> middleware
       * /1234 -> endpoint with param :userId
       * final _reconstructedRoute is /api/v1/:userId
       */
      partialRoute = preventDuplicateSegments(req.originalUrl, req._reconstructedRoute, layer.path) || '';
    }

    // Normalize the partial route so that it doesn't contain leading or trailing slashes
    // and exclude empty or '*' wildcard routes.
    // The exclusion of '*' routes is our best effort to not "pollute" the transaction name
    // with interim handlers (e.g. ones that check authentication or do other middleware stuff).
    // We want to end up with the parameterized URL of the incoming request without any extraneous path segments.
    const finalPartialRoute = partialRoute
      .split('/')
      .filter(segment => segment.length > 0 && (isRegex || isArray || !segment.includes('*')))
      .join('/');

    // If we found a valid partial URL, we append it to the reconstructed route
    if (finalPartialRoute && finalPartialRoute.length > 0) {
      // If the partial route is from a regex route, we append a '/' to close the regex
      req._reconstructedRoute += `/${finalPartialRoute}${isRegex ? '/' : ''}`;
    }

    // Now we check if we are in the "last" part of the route. We determine this by comparing the
    // number of URL segments from the original URL to that of our reconstructed parameterized URL.
    // If we've reached our final destination, we update the transaction name.
    const urlLength = utils.getNumberOfUrlSegments(utils.stripUrlQueryAndFragment(req.originalUrl || '')) + numExtraSegments;
    const routeLength = utils.getNumberOfUrlSegments(req._reconstructedRoute);

    if (urlLength === routeLength) {
      if (!req._hasParameters) {
        if (req._reconstructedRoute !== req.originalUrl) {
          req._reconstructedRoute = req.originalUrl ? utils.stripUrlQueryAndFragment(req.originalUrl) : req.originalUrl;
        }
      }

      const transaction = res.__sentry_transaction;
      if (transaction && transaction.metadata.source !== 'custom') {
        // If the request URL is '/' or empty, the reconstructed route will be empty.
        // Therefore, we fall back to setting the final route to '/' in this case.
        const finalRoute = req._reconstructedRoute || '/';

        transaction.setName(...utils.extractPathForTransaction(req, { path: true, method: true, customRoute: finalRoute }));
      }
    }

    return originalProcessParams.call(this, layer, called, req, res, done);
  };
}

/**
 * Recreate layer.route.path from layer.regexp and layer.keys.
 * Works until express.js used package path-to-regexp@0.1.7
 * or until layer.keys contain offset attribute
 *
 * @param layer the layer to extract the stringified route from
 *
 * @returns string in layer.route.path structure 'router/:pathParam' or undefined
 */
const extractOriginalRoute = (
  path,
  regexp,
  keys,
) => {
  if (!path || !regexp || !keys || Object.keys(keys).length === 0 || !_optionalChain([keys, 'access', _10 => _10[0], 'optionalAccess', _11 => _11.offset])) {
    return undefined;
  }

  const orderedKeys = keys.sort((a, b) => a.offset - b.offset);

  // add d flag for getting indices from regexp result
  const pathRegex = new RegExp(regexp, `${regexp.flags}d`);
  /**
   * use custom type cause of TS error with missing indices in RegExpExecArray
   */
  const execResult = pathRegex.exec(path) ;

  if (!execResult || !execResult.indices) {
    return undefined;
  }
  /**
   * remove first match from regex cause contain whole layer.path
   */
  const [, ...paramIndices] = execResult.indices;

  if (paramIndices.length !== orderedKeys.length) {
    return undefined;
  }
  let resultPath = path;
  let indexShift = 0;

  /**
   * iterate param matches from regexp.exec
   */
  paramIndices.forEach((item, index) => {
    /** check if offsets is define because in some cases regex d flag returns undefined */
    if (item) {
      const [startOffset, endOffset] = item;
      /**
       * isolate part before param
       */
      const substr1 = resultPath.substring(0, startOffset - indexShift);
      /**
       * define paramName as replacement in format :pathParam
       */
      const replacement = `:${orderedKeys[index].name}`;

      /**
       * isolate part after param
       */
      const substr2 = resultPath.substring(endOffset - indexShift);

      /**
       * recreate original path but with param replacement
       */
      resultPath = substr1 + replacement + substr2;

      /**
       * calculate new index shift after resultPath was modified
       */
      indexShift = indexShift + (endOffset - startOffset - replacement.length);
    }
  });

  return resultPath;
};

/**
 * Extracts and stringifies the layer's route which can either be a string with parameters (`users/:id`),
 * a RegEx (`/test/`) or an array of strings and regexes (`['/path1', /\/path[2-5]/, /path/:id]`). Additionally
 * returns extra information about the route, such as if the route is defined as regex or as an array.
 *
 * @param layer the layer to extract the stringified route from
 *
 * @returns an object containing the stringified route, a flag determining if the route was a regex
 *          and the number of extra segments to the matched path that are additionally in the route,
 *          if the route was an array (defaults to 0).
 */
function getLayerRoutePathInfo(layer) {
  let lrp = _optionalChain([layer, 'access', _12 => _12.route, 'optionalAccess', _13 => _13.path]);

  const isRegex = utils.isRegExp(lrp);
  const isArray = Array.isArray(lrp);

  if (!lrp) {
    // parse node.js major version
    // Next.js will complain if we directly use `proces.versions` here because of edge runtime.
    const [major] = (utils.GLOBAL_OBJ ).process.versions.node.split('.').map(Number);

    // allow call extractOriginalRoute only if node version support Regex d flag, node 16+
    if (major >= 16) {
      /**
       * If lrp does not exist try to recreate original layer path from route regexp
       */
      lrp = extractOriginalRoute(layer.path, layer.regexp, layer.keys);
    }
  }

  if (!lrp) {
    return { isRegex, isArray, numExtraSegments: 0 };
  }

  const numExtraSegments = isArray
    ? Math.max(getNumberOfArrayUrlSegments(lrp ) - utils.getNumberOfUrlSegments(layer.path || ''), 0)
    : 0;

  const layerRoutePath = getLayerRoutePathString(isArray, lrp);

  return { layerRoutePath, isRegex, isArray, numExtraSegments };
}

/**
 * Returns the number of URL segments in an array of routes
 *
 * Example: ['/api/test', /\/api\/post[0-9]/, '/users/:id/details`] -> 7
 */
function getNumberOfArrayUrlSegments(routesArray) {
  return routesArray.reduce((accNumSegments, currentRoute) => {
    // array members can be a RegEx -> convert them toString
    return accNumSegments + utils.getNumberOfUrlSegments(currentRoute.toString());
  }, 0);
}

/**
 * Extracts and returns the stringified version of the layers route path
 * Handles route arrays (by joining the paths together) as well as RegExp and normal
 * string values (in the latter case the toString conversion is technically unnecessary but
 * it doesn't hurt us either).
 */
function getLayerRoutePathString(isArray, lrp) {
  if (isArray) {
    return (lrp ).map(r => r.toString()).join(',');
  }
  return lrp && lrp.toString();
}

/**
 * remove duplicate segment contain in layerPath against reconstructedRoute,
 * and return only unique segment that can be added into reconstructedRoute
 */
function preventDuplicateSegments(
  originalUrl,
  reconstructedRoute,
  layerPath,
) {
  // filter query params
  const normalizeURL = utils.stripUrlQueryAndFragment(originalUrl || '');
  const originalUrlSplit = _optionalChain([normalizeURL, 'optionalAccess', _14 => _14.split, 'call', _15 => _15('/'), 'access', _16 => _16.filter, 'call', _17 => _17(v => !!v)]);
  let tempCounter = 0;
  const currentOffset = _optionalChain([reconstructedRoute, 'optionalAccess', _18 => _18.split, 'call', _19 => _19('/'), 'access', _20 => _20.filter, 'call', _21 => _21(v => !!v), 'access', _22 => _22.length]) || 0;
  const result = _optionalChain([layerPath
, 'optionalAccess', _23 => _23.split, 'call', _24 => _24('/')
, 'access', _25 => _25.filter, 'call', _26 => _26(segment => {
      if (_optionalChain([originalUrlSplit, 'optionalAccess', _27 => _27[currentOffset + tempCounter]]) === segment) {
        tempCounter += 1;
        return true;
      }
      return false;
    })
, 'access', _28 => _28.join, 'call', _29 => _29('/')]);
  return result;
}

exports.Express = Express;
exports.extractOriginalRoute = extractOriginalRoute;
exports.preventDuplicateSegments = preventDuplicateSegments;


},{"../../common/debug-build.js":21,"./utils/node-utils.js":33,"@sentry/utils":117}],27:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils');

Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const nodeUtils = require('./utils/node-utils.js');

/** Tracing integration for graphql package */
class GraphQL  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'GraphQL';}

  /**
   * @inheritDoc
   */

   constructor() {
    this.name = GraphQL.id;
  }

  /** @inheritdoc */
   loadDependency() {
    return (this._module = this._module || utils.loadModule('graphql/execution/execute.js'));
  }

  /**
   * @inheritDoc
   */
   setupOnce(_, getCurrentHub) {
    if (nodeUtils.shouldDisableAutoInstrumentation(getCurrentHub)) {
      debugBuild.DEBUG_BUILD && utils.logger.log('GraphQL Integration is skipped because of instrumenter configuration.');
      return;
    }

    const pkg = this.loadDependency();

    if (!pkg) {
      debugBuild.DEBUG_BUILD && utils.logger.error('GraphQL Integration was unable to require graphql/execution package.');
      return;
    }

    utils.fill(pkg, 'execute', function (orig) {
      return function ( ...args) {
        const scope = getCurrentHub().getScope();
        const parentSpan = scope.getSpan();

        const span = _optionalChain([parentSpan, 'optionalAccess', _2 => _2.startChild, 'call', _3 => _3({
          description: 'execute',
          op: 'graphql.execute',
          origin: 'auto.graphql.graphql',
        })]);

        _optionalChain([scope, 'optionalAccess', _4 => _4.setSpan, 'call', _5 => _5(span)]);

        const rv = orig.call(this, ...args);

        if (utils.isThenable(rv)) {
          return rv.then((res) => {
            _optionalChain([span, 'optionalAccess', _6 => _6.finish, 'call', _7 => _7()]);
            _optionalChain([scope, 'optionalAccess', _8 => _8.setSpan, 'call', _9 => _9(parentSpan)]);

            return res;
          });
        }

        _optionalChain([span, 'optionalAccess', _10 => _10.finish, 'call', _11 => _11()]);
        _optionalChain([scope, 'optionalAccess', _12 => _12.setSpan, 'call', _13 => _13(parentSpan)]);
        return rv;
      };
    });
  }
}GraphQL.__initStatic();

exports.GraphQL = GraphQL;


},{"../../common/debug-build.js":21,"./utils/node-utils.js":33,"@sentry/utils":117}],28:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

const lazyLoadedNodePerformanceMonitoringIntegrations = [
  () => {
    const integration = utils.dynamicRequire(module, './apollo')

;
    return new integration.Apollo();
  },
  () => {
    const integration = utils.dynamicRequire(module, './apollo')

;
    return new integration.Apollo({ useNestjs: true });
  },
  () => {
    const integration = utils.dynamicRequire(module, './graphql')

;
    return new integration.GraphQL();
  },
  () => {
    const integration = utils.dynamicRequire(module, './mongo')

;
    return new integration.Mongo();
  },
  () => {
    const integration = utils.dynamicRequire(module, './mongo')

;
    return new integration.Mongo({ mongoose: true });
  },
  () => {
    const integration = utils.dynamicRequire(module, './mysql')

;
    return new integration.Mysql();
  },
  () => {
    const integration = utils.dynamicRequire(module, './postgres')

;
    return new integration.Postgres();
  },
];

exports.lazyLoadedNodePerformanceMonitoringIntegrations = lazyLoadedNodePerformanceMonitoringIntegrations;


},{"@sentry/utils":117}],29:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils');

Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const nodeUtils = require('./utils/node-utils.js');

// This allows us to use the same array for both defaults options and the type itself.
// (note `as const` at the end to make it a union of string literal types (i.e. "a" | "b" | ... )
// and not just a string[])

const OPERATIONS = [
  'aggregate', // aggregate(pipeline, options, callback)
  'bulkWrite', // bulkWrite(operations, options, callback)
  'countDocuments', // countDocuments(query, options, callback)
  'createIndex', // createIndex(fieldOrSpec, options, callback)
  'createIndexes', // createIndexes(indexSpecs, options, callback)
  'deleteMany', // deleteMany(filter, options, callback)
  'deleteOne', // deleteOne(filter, options, callback)
  'distinct', // distinct(key, query, options, callback)
  'drop', // drop(options, callback)
  'dropIndex', // dropIndex(indexName, options, callback)
  'dropIndexes', // dropIndexes(options, callback)
  'estimatedDocumentCount', // estimatedDocumentCount(options, callback)
  'find', // find(query, options, callback)
  'findOne', // findOne(query, options, callback)
  'findOneAndDelete', // findOneAndDelete(filter, options, callback)
  'findOneAndReplace', // findOneAndReplace(filter, replacement, options, callback)
  'findOneAndUpdate', // findOneAndUpdate(filter, update, options, callback)
  'indexes', // indexes(options, callback)
  'indexExists', // indexExists(indexes, options, callback)
  'indexInformation', // indexInformation(options, callback)
  'initializeOrderedBulkOp', // initializeOrderedBulkOp(options, callback)
  'insertMany', // insertMany(docs, options, callback)
  'insertOne', // insertOne(doc, options, callback)
  'isCapped', // isCapped(options, callback)
  'mapReduce', // mapReduce(map, reduce, options, callback)
  'options', // options(options, callback)
  'parallelCollectionScan', // parallelCollectionScan(options, callback)
  'rename', // rename(newName, options, callback)
  'replaceOne', // replaceOne(filter, doc, options, callback)
  'stats', // stats(options, callback)
  'updateMany', // updateMany(filter, update, options, callback)
  'updateOne', // updateOne(filter, update, options, callback)
] ;

// All of the operations above take `options` and `callback` as their final parameters, but some of them
// take additional parameters as well. For those operations, this is a map of
// { <operation name>:  [<names of additional parameters>] }, as a way to know what to call the operation's
// positional arguments when we add them to the span's `data` object later
const OPERATION_SIGNATURES

 = {
  // aggregate intentionally not included because `pipeline` arguments are too complex to serialize well
  // see https://github.com/getsentry/sentry-javascript/pull/3102
  bulkWrite: ['operations'],
  countDocuments: ['query'],
  createIndex: ['fieldOrSpec'],
  createIndexes: ['indexSpecs'],
  deleteMany: ['filter'],
  deleteOne: ['filter'],
  distinct: ['key', 'query'],
  dropIndex: ['indexName'],
  find: ['query'],
  findOne: ['query'],
  findOneAndDelete: ['filter'],
  findOneAndReplace: ['filter', 'replacement'],
  findOneAndUpdate: ['filter', 'update'],
  indexExists: ['indexes'],
  insertMany: ['docs'],
  insertOne: ['doc'],
  mapReduce: ['map', 'reduce'],
  rename: ['newName'],
  replaceOne: ['filter', 'doc'],
  updateMany: ['filter', 'update'],
  updateOne: ['filter', 'update'],
};

function isCursor(maybeCursor) {
  return maybeCursor && typeof maybeCursor === 'object' && maybeCursor.once && typeof maybeCursor.once === 'function';
}

/** Tracing integration for mongo package */
class Mongo  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Mongo';}

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
   constructor(options = {}) {
    this.name = Mongo.id;
    this._operations = Array.isArray(options.operations) ? options.operations : (OPERATIONS );
    this._describeOperations = 'describeOperations' in options ? options.describeOperations : true;
    this._useMongoose = !!options.useMongoose;
  }

  /** @inheritdoc */
   loadDependency() {
    const moduleName = this._useMongoose ? 'mongoose' : 'mongodb';
    return (this._module = this._module || utils.loadModule(moduleName));
  }

  /**
   * @inheritDoc
   */
   setupOnce(_, getCurrentHub) {
    if (nodeUtils.shouldDisableAutoInstrumentation(getCurrentHub)) {
      debugBuild.DEBUG_BUILD && utils.logger.log('Mongo Integration is skipped because of instrumenter configuration.');
      return;
    }

    const pkg = this.loadDependency();

    if (!pkg) {
      const moduleName = this._useMongoose ? 'mongoose' : 'mongodb';
      debugBuild.DEBUG_BUILD && utils.logger.error(`Mongo Integration was unable to require \`${moduleName}\` package.`);
      return;
    }

    this._instrumentOperations(pkg.Collection, this._operations, getCurrentHub);
  }

  /**
   * Patches original collection methods
   */
   _instrumentOperations(collection, operations, getCurrentHub) {
    operations.forEach((operation) => this._patchOperation(collection, operation, getCurrentHub));
  }

  /**
   * Patches original collection to utilize our tracing functionality
   */
   _patchOperation(collection, operation, getCurrentHub) {
    if (!(operation in collection.prototype)) return;

    const getSpanContext = this._getSpanContextFromOperationArguments.bind(this);

    utils.fill(collection.prototype, operation, function (orig) {
      return function ( ...args) {
        const lastArg = args[args.length - 1];
        const scope = getCurrentHub().getScope();
        const parentSpan = scope.getSpan();

        // Check if the operation was passed a callback. (mapReduce requires a different check, as
        // its (non-callback) arguments can also be functions.)
        if (typeof lastArg !== 'function' || (operation === 'mapReduce' && args.length === 2)) {
          const span = _optionalChain([parentSpan, 'optionalAccess', _2 => _2.startChild, 'call', _3 => _3(getSpanContext(this, operation, args))]);
          const maybePromiseOrCursor = orig.call(this, ...args);

          if (utils.isThenable(maybePromiseOrCursor)) {
            return maybePromiseOrCursor.then((res) => {
              _optionalChain([span, 'optionalAccess', _4 => _4.finish, 'call', _5 => _5()]);
              return res;
            });
          }
          // If the operation returns a Cursor
          // we need to attach a listener to it to finish the span when the cursor is closed.
          else if (isCursor(maybePromiseOrCursor)) {
            const cursor = maybePromiseOrCursor ;

            try {
              cursor.once('close', () => {
                _optionalChain([span, 'optionalAccess', _6 => _6.finish, 'call', _7 => _7()]);
              });
            } catch (e) {
              // If the cursor is already closed, `once` will throw an error. In that case, we can
              // finish the span immediately.
              _optionalChain([span, 'optionalAccess', _8 => _8.finish, 'call', _9 => _9()]);
            }

            return cursor;
          } else {
            _optionalChain([span, 'optionalAccess', _10 => _10.finish, 'call', _11 => _11()]);
            return maybePromiseOrCursor;
          }
        }

        const span = _optionalChain([parentSpan, 'optionalAccess', _12 => _12.startChild, 'call', _13 => _13(getSpanContext(this, operation, args.slice(0, -1)))]);

        return orig.call(this, ...args.slice(0, -1), function (err, result) {
          _optionalChain([span, 'optionalAccess', _14 => _14.finish, 'call', _15 => _15()]);
          lastArg(err, result);
        });
      };
    });
  }

  /**
   * Form a SpanContext based on the user input to a given operation.
   */
   _getSpanContextFromOperationArguments(
    collection,
    operation,
    args,
  ) {
    const data = {
      'db.system': 'mongodb',
      'db.name': collection.dbName,
      'db.operation': operation,
      'db.mongodb.collection': collection.collectionName,
    };
    const spanContext = {
      op: 'db',
      // TODO v8: Use `${collection.collectionName}.${operation}`
      origin: 'auto.db.mongo',
      description: operation,
      data,
    };

    // If the operation takes no arguments besides `options` and `callback`, or if argument
    // collection is disabled for this operation, just return early.
    const signature = OPERATION_SIGNATURES[operation];
    const shouldDescribe = Array.isArray(this._describeOperations)
      ? this._describeOperations.includes(operation)
      : this._describeOperations;

    if (!signature || !shouldDescribe) {
      return spanContext;
    }

    try {
      // Special case for `mapReduce`, as the only one accepting functions as arguments.
      if (operation === 'mapReduce') {
        const [map, reduce] = args ;
        data[signature[0]] = typeof map === 'string' ? map : map.name || '<anonymous>';
        data[signature[1]] = typeof reduce === 'string' ? reduce : reduce.name || '<anonymous>';
      } else {
        for (let i = 0; i < signature.length; i++) {
          data[`db.mongodb.${signature[i]}`] = JSON.stringify(args[i]);
        }
      }
    } catch (_oO) {
      // no-empty
    }

    return spanContext;
  }
}Mongo.__initStatic();

exports.Mongo = Mongo;


},{"../../common/debug-build.js":21,"./utils/node-utils.js":33,"@sentry/utils":117}],30:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils');

Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const nodeUtils = require('./utils/node-utils.js');

/** Tracing integration for node-mysql package */
class Mysql  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Mysql';}

  /**
   * @inheritDoc
   */

   constructor() {
    this.name = Mysql.id;
  }

  /** @inheritdoc */
   loadDependency() {
    return (this._module = this._module || utils.loadModule('mysql/lib/Connection.js'));
  }

  /**
   * @inheritDoc
   */
   setupOnce(_, getCurrentHub) {
    if (nodeUtils.shouldDisableAutoInstrumentation(getCurrentHub)) {
      debugBuild.DEBUG_BUILD && utils.logger.log('Mysql Integration is skipped because of instrumenter configuration.');
      return;
    }

    const pkg = this.loadDependency();

    if (!pkg) {
      debugBuild.DEBUG_BUILD && utils.logger.error('Mysql Integration was unable to require `mysql` package.');
      return;
    }

    let mySqlConfig = undefined;

    try {
      pkg.prototype.connect = new Proxy(pkg.prototype.connect, {
        apply(wrappingTarget, thisArg, args) {
          if (!mySqlConfig) {
            mySqlConfig = thisArg.config;
          }
          return wrappingTarget.apply(thisArg, args);
        },
      });
    } catch (e) {
      debugBuild.DEBUG_BUILD && utils.logger.error('Mysql Integration was unable to instrument `mysql` config.');
    }

    function spanDataFromConfig() {
      if (!mySqlConfig) {
        return {};
      }
      return {
        'server.address': mySqlConfig.host,
        'server.port': mySqlConfig.port,
        'db.user': mySqlConfig.user,
      };
    }

    function finishSpan(span) {
      if (!span || span.endTimestamp) {
        return;
      }

      const data = spanDataFromConfig();
      Object.keys(data).forEach(key => {
        span.setData(key, data[key]);
      });

      span.finish();
    }

    // The original function will have one of these signatures:
    //    function (callback) => void
    //    function (options, callback) => void
    //    function (options, values, callback) => void
    utils.fill(pkg, 'createQuery', function (orig) {
      return function ( options, values, callback) {
        const scope = getCurrentHub().getScope();
        const parentSpan = scope.getSpan();

        const span = _optionalChain([parentSpan, 'optionalAccess', _2 => _2.startChild, 'call', _3 => _3({
          description: typeof options === 'string' ? options : (options ).sql,
          op: 'db',
          origin: 'auto.db.mysql',
          data: {
            'db.system': 'mysql',
          },
        })]);

        if (typeof callback === 'function') {
          return orig.call(this, options, values, function (err, result, fields) {
            finishSpan(span);
            callback(err, result, fields);
          });
        }

        if (typeof values === 'function') {
          return orig.call(this, options, function (err, result, fields) {
            finishSpan(span);
            values(err, result, fields);
          });
        }

        // streaming, no callback!
        const query = orig.call(this, options, values) ;

        query.on('end', () => {
          finishSpan(span);
        });

        return query;
      };
    });
  }
}Mysql.__initStatic();

exports.Mysql = Mysql;


},{"../../common/debug-build.js":21,"./utils/node-utils.js":33,"@sentry/utils":117}],31:[function(require,module,exports){
var {
  _optionalChain
} = require('@sentry/utils');

Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const nodeUtils = require('./utils/node-utils.js');

/** Tracing integration for node-postgres package */
class Postgres  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Postgres';}

  /**
   * @inheritDoc
   */

   constructor(options = {}) {
    this.name = Postgres.id;
    this._usePgNative = !!options.usePgNative;
    this._module = options.module;
  }

  /** @inheritdoc */
   loadDependency() {
    return (this._module = this._module || utils.loadModule('pg'));
  }

  /**
   * @inheritDoc
   */
   setupOnce(_, getCurrentHub) {
    if (nodeUtils.shouldDisableAutoInstrumentation(getCurrentHub)) {
      debugBuild.DEBUG_BUILD && utils.logger.log('Postgres Integration is skipped because of instrumenter configuration.');
      return;
    }

    const pkg = this.loadDependency();

    if (!pkg) {
      debugBuild.DEBUG_BUILD && utils.logger.error('Postgres Integration was unable to require `pg` package.');
      return;
    }

    const Client = this._usePgNative ? _optionalChain([pkg, 'access', _2 => _2.native, 'optionalAccess', _3 => _3.Client]) : pkg.Client;

    if (!Client) {
      debugBuild.DEBUG_BUILD && utils.logger.error("Postgres Integration was unable to access 'pg-native' bindings.");
      return;
    }

    /**
     * function (query, callback) => void
     * function (query, params, callback) => void
     * function (query) => Promise
     * function (query, params) => Promise
     * function (pg.Cursor) => pg.Cursor
     */
    utils.fill(Client.prototype, 'query', function (orig) {
      return function ( config, values, callback) {
        const scope = getCurrentHub().getScope();
        const parentSpan = scope.getSpan();

        const data = {
          'db.system': 'postgresql',
        };

        try {
          if (this.database) {
            data['db.name'] = this.database;
          }
          if (this.host) {
            data['server.address'] = this.host;
          }
          if (this.port) {
            data['server.port'] = this.port;
          }
          if (this.user) {
            data['db.user'] = this.user;
          }
        } catch (e) {
          // ignore
        }

        const span = _optionalChain([parentSpan, 'optionalAccess', _4 => _4.startChild, 'call', _5 => _5({
          description: typeof config === 'string' ? config : (config ).text,
          op: 'db',
          origin: 'auto.db.postgres',
          data,
        })]);

        if (typeof callback === 'function') {
          return orig.call(this, config, values, function (err, result) {
            _optionalChain([span, 'optionalAccess', _6 => _6.finish, 'call', _7 => _7()]);
            callback(err, result);
          });
        }

        if (typeof values === 'function') {
          return orig.call(this, config, function (err, result) {
            _optionalChain([span, 'optionalAccess', _8 => _8.finish, 'call', _9 => _9()]);
            values(err, result);
          });
        }

        const rv = typeof values !== 'undefined' ? orig.call(this, config, values) : orig.call(this, config);

        if (utils.isThenable(rv)) {
          return rv.then((res) => {
            _optionalChain([span, 'optionalAccess', _10 => _10.finish, 'call', _11 => _11()]);
            return res;
          });
        }

        _optionalChain([span, 'optionalAccess', _12 => _12.finish, 'call', _13 => _13()]);
        return rv;
      };
    });
  }
}Postgres.__initStatic();

exports.Postgres = Postgres;


},{"../../common/debug-build.js":21,"./utils/node-utils.js":33,"@sentry/utils":117}],32:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('../../common/debug-build.js');
const nodeUtils = require('./utils/node-utils.js');

function isValidPrismaClient(possibleClient) {
  return !!possibleClient && !!(possibleClient )['$use'];
}

/** Tracing integration for @prisma/client package */
class Prisma  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Prisma';}

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
   constructor(options = {}) {
    this.name = Prisma.id;

    // We instrument the PrismaClient inside the constructor and not inside `setupOnce` because in some cases of server-side
    // bundling (Next.js) multiple Prisma clients can be instantiated, even though users don't intend to. When instrumenting
    // in setupOnce we can only ever instrument one client.
    // https://github.com/getsentry/sentry-javascript/issues/7216#issuecomment-1602375012
    // In the future we might explore providing a dedicated PrismaClient middleware instead of this hack.
    if (isValidPrismaClient(options.client) && !options.client._sentryInstrumented) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      utils.addNonEnumerableProperty(options.client , '_sentryInstrumented', true);

      const clientData = {};
      try {
        const engineConfig = (options.client )._engineConfig;
        if (engineConfig) {
          const { activeProvider, clientVersion } = engineConfig;
          if (activeProvider) {
            clientData['db.system'] = activeProvider;
          }
          if (clientVersion) {
            clientData['db.prisma.version'] = clientVersion;
          }
        }
      } catch (e) {
        // ignore
      }

      options.client.$use((params, next) => {
        if (nodeUtils.shouldDisableAutoInstrumentation(core.getCurrentHub)) {
          return next(params);
        }

        const action = params.action;
        const model = params.model;

        return core.trace(
          {
            name: model ? `${model} ${action}` : action,
            op: 'db.prisma',
            origin: 'auto.db.prisma',
            data: { ...clientData, 'db.operation': action },
          },
          () => next(params),
        );
      });
    } else {
      debugBuild.DEBUG_BUILD &&
        utils.logger.warn('Unsupported Prisma client provided to PrismaIntegration. Provided client:', options.client);
    }
  }

  /**
   * @inheritDoc
   */
   setupOnce() {
    // Noop - here for backwards compatibility
  }
} Prisma.__initStatic();

exports.Prisma = Prisma;


},{"../../common/debug-build.js":21,"./utils/node-utils.js":33,"@sentry/core":65,"@sentry/utils":117}],33:[function(require,module,exports){
var {
 _optionalChain
} = require('@sentry/utils');

Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Check if Sentry auto-instrumentation should be disabled.
 *
 * @param getCurrentHub A method to fetch the current hub
 * @returns boolean
 */
function shouldDisableAutoInstrumentation(getCurrentHub) {
  const clientOptions = _optionalChain([getCurrentHub, 'call', _ => _(), 'access', _2 => _2.getClient, 'call', _3 => _3(), 'optionalAccess', _4 => _4.getOptions, 'call', _5 => _5()]);
  const instrumenter = _optionalChain([clientOptions, 'optionalAccess', _6 => _6.instrumenter]) || 'sentry';

  return instrumenter !== 'sentry';
}

exports.shouldDisableAutoInstrumentation = shouldDisableAutoInstrumentation;


},{"@sentry/utils":117}],34:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('./debug-build.js');
const eventbuilder = require('./eventbuilder.js');
const helpers = require('./helpers.js');
const userfeedback = require('./userfeedback.js');

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
    const sdkSource = helpers.WINDOW.SENTRY_SDK_SOURCE || utils.getSDKSource();

    options._metadata = options._metadata || {};
    options._metadata.sdk = options._metadata.sdk || {
      name: 'sentry.javascript.browser',
      packages: [
        {
          name: `${sdkSource}:@sentry/browser`,
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
   * Sends user feedback to Sentry.
   */
   captureUserFeedback(feedback) {
    if (!this._isEnabled()) {
      debugBuild.DEBUG_BUILD && utils.logger.warn('SDK not enabled, will not capture user feedback.');
      return;
    }

    const envelope = userfeedback.createUserFeedbackEnvelope(feedback, {
      metadata: this.getSdkMetadata(),
      dsn: this.getDsn(),
      tunnel: this.getOptions().tunnel,
    });
    void this._sendEnvelope(envelope);
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
      debugBuild.DEBUG_BUILD && utils.logger.log('No outcomes to send');
      return;
    }

    // This is really the only place where we want to check for a DSN and only send outcomes then
    if (!this._dsn) {
      debugBuild.DEBUG_BUILD && utils.logger.log('No dsn provided, will not send outcomes');
      return;
    }

    debugBuild.DEBUG_BUILD && utils.logger.log('Sending outcomes:', outcomes);

    const envelope = utils.createClientReportEnvelope(outcomes, this._options.tunnel && utils.dsnToString(this._dsn));
    void this._sendEnvelope(envelope);
  }
}

exports.BrowserClient = BrowserClient;


},{"./debug-build.js":35,"./eventbuilder.js":36,"./helpers.js":37,"./userfeedback.js":55,"@sentry/core":65,"@sentry/utils":117}],35:[function(require,module,exports){
arguments[4][21][0].apply(exports,arguments)
},{"dup":21}],36:[function(require,module,exports){
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
          value: getNonErrorObjectExceptionValue(exception, { isUnhandledRejection }),
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
  if (utils.isDOMError(exception) || utils.isDOMException(exception )) {
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
      // eslint-disable-next-line deprecation/deprecation
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

function getNonErrorObjectExceptionValue(
  exception,
  { isUnhandledRejection },
) {
  const keys = utils.extractExceptionKeysForMessage(exception);
  const captureType = isUnhandledRejection ? 'promise rejection' : 'exception';

  // Some ErrorEvent instances do not have an `error` property, which is why they are not handled before
  // We still want to try to get a decent message for these cases
  if (utils.isErrorEvent(exception)) {
    return `Event \`ErrorEvent\` captured as ${captureType} with message \`${exception.message}\``;
  }

  if (utils.isEvent(exception)) {
    const className = getObjectClassName(exception);
    return `Event \`${className}\` (type=${exception.type}) captured as ${captureType}`;
  }

  return `Object captured as ${captureType} with keys: ${keys}`;
}

function getObjectClassName(obj) {
  try {
    const prototype = Object.getPrototypeOf(obj);
    return prototype ? prototype.constructor.name : undefined;
  } catch (e) {
    // ignore errors here
  }
}

exports.eventFromError = eventFromError;
exports.eventFromException = eventFromException;
exports.eventFromMessage = eventFromMessage;
exports.eventFromPlainObject = eventFromPlainObject;
exports.eventFromString = eventFromString;
exports.eventFromUnknownInput = eventFromUnknownInput;
exports.exceptionFromError = exceptionFromError;
exports.parseStackFrames = parseStackFrames;


},{"@sentry/core":65,"@sentry/utils":117}],37:[function(require,module,exports){
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

      core.withScope(scope => {
        scope.addEventProcessor(event => {
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


},{"@sentry/core":65,"@sentry/utils":117}],38:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const helpers = require('./helpers.js');
const client = require('./client.js');
const fetch = require('./transports/fetch.js');
const xhr = require('./transports/xhr.js');
const stackParsers = require('./stack-parsers.js');
const eventbuilder = require('./eventbuilder.js');
const userfeedback = require('./userfeedback.js');
const sdk = require('./sdk.js');
const index = require('./integrations/index.js');
const replay = require('@sentry/replay');
const feedback = require('@sentry-internal/feedback');
const tracing = require('@sentry-internal/tracing');
const offline = require('./transports/offline.js');
const hubextensions = require('./profiling/hubextensions.js');
const integration = require('./profiling/integration.js');
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

exports.FunctionToString = core.FunctionToString;
exports.Hub = core.Hub;
exports.InboundFilters = core.InboundFilters;
exports.ModuleMetadata = core.ModuleMetadata;
exports.SDK_VERSION = core.SDK_VERSION;
exports.Scope = core.Scope;
exports.addBreadcrumb = core.addBreadcrumb;
exports.addEventProcessor = core.addEventProcessor;
exports.addGlobalEventProcessor = core.addGlobalEventProcessor;
exports.addIntegration = core.addIntegration;
exports.addTracingExtensions = core.addTracingExtensions;
exports.captureEvent = core.captureEvent;
exports.captureException = core.captureException;
exports.captureMessage = core.captureMessage;
exports.close = core.close;
exports.configureScope = core.configureScope;
exports.continueTrace = core.continueTrace;
exports.createTransport = core.createTransport;
exports.extractTraceparentData = core.extractTraceparentData;
exports.flush = core.flush;
exports.getActiveSpan = core.getActiveSpan;
exports.getActiveTransaction = core.getActiveTransaction;
exports.getClient = core.getClient;
exports.getCurrentHub = core.getCurrentHub;
exports.getHubFromCarrier = core.getHubFromCarrier;
exports.lastEventId = core.lastEventId;
exports.makeMain = core.makeMain;
exports.makeMultiplexedTransport = core.makeMultiplexedTransport;
exports.setContext = core.setContext;
exports.setExtra = core.setExtra;
exports.setExtras = core.setExtras;
exports.setMeasurement = core.setMeasurement;
exports.setTag = core.setTag;
exports.setTags = core.setTags;
exports.setUser = core.setUser;
exports.spanStatusfromHttpCode = core.spanStatusfromHttpCode;
exports.startInactiveSpan = core.startInactiveSpan;
exports.startSpan = core.startSpan;
exports.startSpanManual = core.startSpanManual;
exports.startTransaction = core.startTransaction;
exports.trace = core.trace;
exports.withScope = core.withScope;
exports.WINDOW = helpers.WINDOW;
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
exports.exceptionFromError = eventbuilder.exceptionFromError;
exports.createUserFeedbackEnvelope = userfeedback.createUserFeedbackEnvelope;
exports.captureUserFeedback = sdk.captureUserFeedback;
exports.defaultIntegrations = sdk.defaultIntegrations;
exports.forceLoad = sdk.forceLoad;
exports.init = sdk.init;
exports.onLoad = sdk.onLoad;
exports.showReportDialog = sdk.showReportDialog;
exports.wrap = sdk.wrap;
exports.Replay = replay.Replay;
exports.Feedback = feedback.Feedback;
exports.BrowserTracing = tracing.BrowserTracing;
exports.defaultRequestInstrumentationOptions = tracing.defaultRequestInstrumentationOptions;
exports.instrumentOutgoingRequests = tracing.instrumentOutgoingRequests;
exports.makeBrowserOfflineTransport = offline.makeBrowserOfflineTransport;
exports.onProfilingStartRouteTransaction = hubextensions.onProfilingStartRouteTransaction;
exports.BrowserProfilingIntegration = integration.BrowserProfilingIntegration;
exports.GlobalHandlers = globalhandlers.GlobalHandlers;
exports.TryCatch = trycatch.TryCatch;
exports.Breadcrumbs = breadcrumbs.Breadcrumbs;
exports.LinkedErrors = linkederrors.LinkedErrors;
exports.HttpContext = httpcontext.HttpContext;
exports.Dedupe = dedupe.Dedupe;
exports.Integrations = INTEGRATIONS;


},{"./client.js":34,"./eventbuilder.js":36,"./helpers.js":37,"./integrations/breadcrumbs.js":39,"./integrations/dedupe.js":40,"./integrations/globalhandlers.js":41,"./integrations/httpcontext.js":42,"./integrations/index.js":43,"./integrations/linkederrors.js":44,"./integrations/trycatch.js":45,"./profiling/hubextensions.js":46,"./profiling/integration.js":47,"./sdk.js":49,"./stack-parsers.js":50,"./transports/fetch.js":51,"./transports/offline.js":52,"./transports/xhr.js":54,"./userfeedback.js":55,"@sentry-internal/feedback":1,"@sentry-internal/tracing":24,"@sentry/core":65,"@sentry/replay":97}],39:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const helpers = require('../helpers.js');
require('../stack-parsers.js');
require('../sdk.js');
require('./globalhandlers.js');
require('./trycatch.js');
require('./linkederrors.js');
require('./httpcontext.js');
require('./dedupe.js');

/* eslint-disable max-lines */

/** JSDoc */

/** maxStringLength gets capped to prevent 100 breadcrumbs exceeding 1MB event payload size */
const MAX_ALLOWED_STRING_LENGTH = 1024;

/**
 * Default Breadcrumbs instrumentations
 * TODO: Deprecated - with v6, this will be renamed to `Instrument`
 */
class Breadcrumbs  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Breadcrumbs';}

  /**
   * @inheritDoc
   */

  /**
   * Options of the breadcrumbs integration.
   */
  // This field is public, because we use it in the browser client to check if the `sentry` option is enabled.

  /**
   * @inheritDoc
   */
   constructor(options) {
    this.name = Breadcrumbs.id;
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
      utils.addConsoleInstrumentationHandler(_consoleBreadcrumb);
    }
    if (this.options.dom) {
      utils.addClickKeypressInstrumentationHandler(_domBreadcrumb(this.options.dom));
    }
    if (this.options.xhr) {
      utils.addXhrInstrumentationHandler(_xhrBreadcrumb);
    }
    if (this.options.fetch) {
      utils.addFetchInstrumentationHandler(_fetchBreadcrumb);
    }
    if (this.options.history) {
      utils.addHistoryInstrumentationHandler(_historyBreadcrumb);
    }
    if (this.options.sentry) {
      const client = core.getClient();
      client && client.on && client.on('beforeSendEvent', addSentryBreadcrumb);
    }
  }
} Breadcrumbs.__initStatic();

/**
 * Adds a breadcrumb for Sentry events or transactions if this option is enabled.
 */
function addSentryBreadcrumb(event) {
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

/**
 * A HOC that creaes a function that creates breadcrumbs from DOM API calls.
 * This is a HOC so that we get access to dom options in the closure.
 */
function _domBreadcrumb(dom) {
  function _innerDomBreadcrumb(handlerData) {
    let target;
    let keyAttrs = typeof dom === 'object' ? dom.serializeAttribute : undefined;

    let maxStringLength =
      typeof dom === 'object' && typeof dom.maxStringLength === 'number' ? dom.maxStringLength : undefined;
    if (maxStringLength && maxStringLength > MAX_ALLOWED_STRING_LENGTH) {
      debugBuild.DEBUG_BUILD &&
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
      const event = handlerData.event ;
      target = _isEvent(event)
        ? utils.htmlTreeAsString(event.target, { keyAttrs, maxStringLength })
        : utils.htmlTreeAsString(event, { keyAttrs, maxStringLength });
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
function _consoleBreadcrumb(handlerData) {
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
function _xhrBreadcrumb(handlerData) {
  const { startTimestamp, endTimestamp } = handlerData;

  const sentryXhrData = handlerData.xhr[utils.SENTRY_XHR_DATA_KEY];

  // We only capture complete, non-sentry requests
  if (!startTimestamp || !endTimestamp || !sentryXhrData) {
    return;
  }

  const { method, url, status_code, body } = sentryXhrData;

  const data = {
    method,
    url,
    status_code,
  };

  const hint = {
    xhr: handlerData.xhr,
    input: body,
    startTimestamp,
    endTimestamp,
  };

  core.getCurrentHub().addBreadcrumb(
    {
      category: 'xhr',
      data,
      type: 'http',
    },
    hint,
  );
}

/**
 * Creates breadcrumbs from fetch API calls
 */
function _fetchBreadcrumb(handlerData) {
  const { startTimestamp, endTimestamp } = handlerData;

  // We only capture complete fetch requests
  if (!endTimestamp) {
    return;
  }

  if (handlerData.fetchData.url.match(/sentry_key/) && handlerData.fetchData.method === 'POST') {
    // We will not create breadcrumbs for fetch requests that contain `sentry_key` (internal sentry requests)
    return;
  }

  if (handlerData.error) {
    const data = handlerData.fetchData;
    const hint = {
      data: handlerData.error,
      input: handlerData.args,
      startTimestamp,
      endTimestamp,
    };

    core.getCurrentHub().addBreadcrumb(
      {
        category: 'fetch',
        data,
        level: 'error',
        type: 'http',
      },
      hint,
    );
  } else {
    const response = handlerData.response ;
    const data = {
      ...handlerData.fetchData,
      status_code: response && response.status,
    };
    const hint = {
      input: handlerData.args,
      response,
      startTimestamp,
      endTimestamp,
    };
    core.getCurrentHub().addBreadcrumb(
      {
        category: 'fetch',
        data,
        type: 'http',
      },
      hint,
    );
  }
}

/**
 * Creates breadcrumbs from history API calls
 */
function _historyBreadcrumb(handlerData) {
  let from = handlerData.from;
  let to = handlerData.to;
  const parsedLoc = utils.parseUrl(helpers.WINDOW.location.href);
  let parsedFrom = from ? utils.parseUrl(from) : undefined;
  const parsedTo = utils.parseUrl(to);

  // Initial pushState doesn't provide `from` information
  if (!parsedFrom || !parsedFrom.path) {
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

function _isEvent(event) {
  return !!event && !!(event ).target;
}

exports.Breadcrumbs = Breadcrumbs;


},{"../debug-build.js":35,"../helpers.js":37,"../sdk.js":49,"../stack-parsers.js":50,"./dedupe.js":40,"./globalhandlers.js":41,"./httpcontext.js":42,"./linkederrors.js":44,"./trycatch.js":45,"@sentry/core":65,"@sentry/utils":117}],40:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');

/** Deduplication filter */
class Dedupe  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Dedupe';}

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

   constructor() {
    this.name = Dedupe.id;
  }

  /** @inheritDoc */
   setupOnce(_addGlobalEventProcessor, _getCurrentHub) {
    // noop
  }

  /**
   * @inheritDoc
   */
   processEvent(currentEvent) {
    // We want to ignore any non-error type events, e.g. transactions or replays
    // These should never be deduped, and also not be compared against as _previousEvent.
    if (currentEvent.type) {
      return currentEvent;
    }

    // Juuust in case something goes wrong
    try {
      if (_shouldDropEvent(currentEvent, this._previousEvent)) {
        debugBuild.DEBUG_BUILD && utils.logger.warn('Event dropped due to being a duplicate of previously captured event.');
        return null;
      }
    } catch (_oO) {} // eslint-disable-line no-empty

    return (this._previousEvent = currentEvent);
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
      // @ts-expect-error Object could be undefined
      return exception.values[0].stacktrace.frames;
    } catch (_oO) {
      return undefined;
    }
  }
  return undefined;
}

exports.Dedupe = Dedupe;


},{"../debug-build.js":35,"@sentry/utils":117}],41:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
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

  /** JSDoc */

  /**
   * Stores references functions to installing handlers. Will set to undefined
   * after they have been run so that they are not used twice.
   */

  /** JSDoc */
   constructor(options) {
    this.name = GlobalHandlers.id;
    this._options = {
      onerror: true,
      onunhandledrejection: true,
      ...options,
    };

    this._installFunc = {
      onerror: _installGlobalOnErrorHandler,
      onunhandledrejection: _installGlobalOnUnhandledRejectionHandler,
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

function _installGlobalOnErrorHandler() {
  utils.addGlobalErrorInstrumentationHandler(data => {
    const [hub, stackParser, attachStacktrace] = getHubAndOptions();
    if (!hub.getIntegration(GlobalHandlers)) {
      return;
    }
    const { msg, url, line, column, error } = data;
    if (helpers.shouldIgnoreOnError()) {
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

    hub.captureEvent(event, {
      originalException: error,
      mechanism: {
        handled: false,
        type: 'onerror',
      },
    });
  });
}

function _installGlobalOnUnhandledRejectionHandler() {
  utils.addGlobalUnhandledRejectionInstrumentationHandler(e => {
    const [hub, stackParser, attachStacktrace] = getHubAndOptions();
    if (!hub.getIntegration(GlobalHandlers)) {
      return;
    }

    if (helpers.shouldIgnoreOnError()) {
      return true;
    }

    const error = _getUnhandledRejectionError(e );

    const event = utils.isPrimitive(error)
      ? _eventFromRejectionWithPrimitive(error)
      : eventbuilder.eventFromUnknownInput(stackParser, error, undefined, attachStacktrace, true);

    event.level = 'error';

    hub.captureEvent(event, {
      originalException: error,
      mechanism: {
        handled: false,
        type: 'onunhandledrejection',
      },
    });

    return;
  });
}

function _getUnhandledRejectionError(error) {
  if (utils.isPrimitive(error)) {
    return error;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const e = error ;

  // dig the object of the rejection out of known event types
  try {
    // PromiseRejectionEvents store the object of the rejection under 'reason'
    // see https://developer.mozilla.org/en-US/docs/Web/API/PromiseRejectionEvent
    if ('reason' in e) {
      return e.reason;
    }

    // something, somewhere, (likely a browser extension) effectively casts PromiseRejectionEvents
    // to CustomEvents, moving the `promise` and `reason` attributes of the PRE into
    // the CustomEvent's `detail` attribute, since they're not part of CustomEvent's spec
    // see https://developer.mozilla.org/en-US/docs/Web/API/CustomEvent and
    // https://github.com/getsentry/sentry-javascript/issues/2380
    else if ('detail' in e && 'reason' in e.detail) {
      return e.detail.reason;
    }
  } catch (e2) {} // eslint-disable-line no-empty

  return error;
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
  debugBuild.DEBUG_BUILD && utils.logger.log(`Global Handler attached: ${type}`);
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


},{"../debug-build.js":35,"../eventbuilder.js":36,"../helpers.js":37,"@sentry/core":65,"@sentry/utils":117}],42:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const helpers = require('../helpers.js');

/** HttpContext integration collects information about HTTP request headers */
class HttpContext  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'HttpContext';}

  /**
   * @inheritDoc
   */

   constructor() {
    this.name = HttpContext.id;
  }

  /**
   * @inheritDoc
   */
   setupOnce() {
    // noop
  }

  /** @inheritDoc */
   preprocessEvent(event) {
    // if none of the information we want exists, don't bother
    if (!helpers.WINDOW.navigator && !helpers.WINDOW.location && !helpers.WINDOW.document) {
      return;
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
    const request = { ...event.request, ...(url && { url }), headers };

    event.request = request;
  }
} HttpContext.__initStatic();

exports.HttpContext = HttpContext;


},{"../helpers.js":37}],43:[function(require,module,exports){
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


},{"./breadcrumbs.js":39,"./dedupe.js":40,"./globalhandlers.js":41,"./httpcontext.js":42,"./linkederrors.js":44,"./trycatch.js":45}],44:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

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

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
   constructor(options = {}) {
    this.name = LinkedErrors.id;
    this._key = options.key || DEFAULT_KEY;
    this._limit = options.limit || DEFAULT_LIMIT;
  }

  /** @inheritdoc */
   setupOnce() {
    // noop
  }

  /**
   * @inheritDoc
   */
   preprocessEvent(event, hint, client) {
    const options = client.getOptions();

    utils.applyAggregateErrorsToEvent(
      eventbuilder.exceptionFromError,
      options.stackParser,
      options.maxValueLength,
      this._key,
      this._limit,
      event,
      hint,
    );
  }
} LinkedErrors.__initStatic();

exports.LinkedErrors = LinkedErrors;


},{"../eventbuilder.js":36,"@sentry/utils":117}],45:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const helpers = require('../helpers.js');

const DEFAULT_EVENT_TARGET = [
  'EventTarget',
  'Window',
  'Node',
  'ApplicationCache',
  'AudioTrackList',
  'BroadcastChannel',
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
  'SharedWorker',
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

  /** JSDoc */

  /**
   * @inheritDoc
   */
   constructor(options) {
    this.name = TryCatch.id;
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
        handled: false,
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
          handled: false,
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
              handled: false,
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

  utils.fill(proto, 'addEventListener', function (original,)

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
              handled: false,
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
            handled: false,
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


},{"../helpers.js":37,"@sentry/utils":117}],46:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const helpers = require('../helpers.js');
const utils$1 = require('./utils.js');

/**
 * Safety wrapper for startTransaction for the unlikely case that transaction starts before tracing is imported -
 * if that happens we want to avoid throwing an error from profiling code.
 * see https://github.com/getsentry/sentry-javascript/issues/4731.
 *
 * @experimental
 */
function onProfilingStartRouteTransaction(transaction) {
  if (!transaction) {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log('[Profiling] Transaction is undefined, skipping profiling');
    }
    return transaction;
  }

  if (utils$1.shouldProfileTransaction(transaction)) {
    return startProfileForTransaction(transaction);
  }

  return transaction;
}

/**
 * Wraps startTransaction and stopTransaction with profiling related logic.
 * startProfileForTransaction is called after the call to startTransaction in order to avoid our own code from
 * being profiled. Because of that same reason, stopProfiling is called before the call to stopTransaction.
 */
function startProfileForTransaction(transaction) {
  // Start the profiler and get the profiler instance.
  let startTimestamp;
  if (utils$1.isAutomatedPageLoadTransaction(transaction)) {
    startTimestamp = utils.timestampInSeconds() * 1000;
  }

  const profiler = utils$1.startJSSelfProfile();

  // We failed to construct the profiler, fallback to original transaction.
  // No need to log anything as this has already been logged in startProfile.
  if (!profiler) {
    return transaction;
  }

  if (debugBuild.DEBUG_BUILD) {
    utils.logger.log(`[Profiling] started profiling transaction: ${transaction.name || transaction.description}`);
  }

  // We create "unique" transaction names to avoid concurrent transactions with same names
  // from being ignored by the profiler. From here on, only this transaction name should be used when
  // calling the profiler methods. Note: we log the original name to the user to avoid confusion.
  const profileId = utils.uuid4();

  /**
   * Idempotent handler for profile stop
   */
  async function onProfileHandler() {
    // Check if the profile exists and return it the behavior has to be idempotent as users may call transaction.finish multiple times.
    if (!transaction) {
      return null;
    }
    // Satisfy the type checker, but profiler will always be defined here.
    if (!profiler) {
      return null;
    }

    return profiler
      .stop()
      .then((profile) => {
        if (maxDurationTimeoutID) {
          helpers.WINDOW.clearTimeout(maxDurationTimeoutID);
          maxDurationTimeoutID = undefined;
        }

        if (debugBuild.DEBUG_BUILD) {
          utils.logger.log(`[Profiling] stopped profiling of transaction: ${transaction.name || transaction.description}`);
        }

        // In case of an overlapping transaction, stopProfiling may return null and silently ignore the overlapping profile.
        if (!profile) {
          if (debugBuild.DEBUG_BUILD) {
            utils.logger.log(
              `[Profiling] profiler returned null profile for: ${transaction.name || transaction.description}`,
              'this may indicate an overlapping transaction or a call to stopProfiling with a profile title that was never started',
            );
          }
          return null;
        }

        utils$1.addProfileToGlobalCache(profileId, profile);
        return null;
      })
      .catch(error => {
        if (debugBuild.DEBUG_BUILD) {
          utils.logger.log('[Profiling] error while stopping profiler:', error);
        }
        return null;
      });
  }

  // Enqueue a timeout to prevent profiles from running over max duration.
  let maxDurationTimeoutID = helpers.WINDOW.setTimeout(() => {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log(
        '[Profiling] max profile duration elapsed, stopping profiling for:',
        transaction.name || transaction.description,
      );
    }
    // If the timeout exceeds, we want to stop profiling, but not finish the transaction
    void onProfileHandler();
  }, utils$1.MAX_PROFILE_DURATION_MS);

  // We need to reference the original finish call to avoid creating an infinite loop
  const originalFinish = transaction.finish.bind(transaction);

  /**
   * Wraps startTransaction and stopTransaction with profiling related logic.
   * startProfiling is called after the call to startTransaction in order to avoid our own code from
   * being profiled. Because of that same reason, stopProfiling is called before the call to stopTransaction.
   */
  function profilingWrappedTransactionFinish() {
    if (!transaction) {
      return originalFinish();
    }
    // onProfileHandler should always return the same profile even if this is called multiple times.
    // Always call onProfileHandler to ensure stopProfiling is called and the timeout is cleared.
    void onProfileHandler().then(
      () => {
        transaction.setContext('profile', { profile_id: profileId, start_timestamp: startTimestamp });
        originalFinish();
      },
      () => {
        // If onProfileHandler fails, we still want to call the original finish method.
        originalFinish();
      },
    );

    return transaction;
  }

  transaction.finish = profilingWrappedTransactionFinish;
  return transaction;
}

exports.onProfilingStartRouteTransaction = onProfilingStartRouteTransaction;
exports.startProfileForTransaction = startProfileForTransaction;


},{"../debug-build.js":35,"../helpers.js":37,"./utils.js":48,"@sentry/utils":117}],47:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils$1 = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const hubextensions = require('./hubextensions.js');
const utils = require('./utils.js');

/**
 * Browser profiling integration. Stores any event that has contexts["profile"]["profile_id"]
 * This exists because we do not want to await async profiler.stop calls as transaction.finish is called
 * in a synchronous context. Instead, we handle sending the profile async from the promise callback and
 * rely on being able to pull the event from the cache when we need to construct the envelope. This makes the
 * integration less reliable as we might be dropping profiles when the cache is full.
 *
 * @experimental
 */
class BrowserProfilingIntegration  {
   static __initStatic() {this.id = 'BrowserProfilingIntegration';}

   constructor() {
    this.name = BrowserProfilingIntegration.id;
  }

  /**
   * @inheritDoc
   */
   setupOnce(_addGlobalEventProcessor, getCurrentHub) {
    this.getCurrentHub = getCurrentHub;

    const hub = this.getCurrentHub();
    const client = hub.getClient();
    const scope = hub.getScope();

    const transaction = scope.getTransaction();

    if (transaction && utils.isAutomatedPageLoadTransaction(transaction)) {
      if (utils.shouldProfileTransaction(transaction)) {
        hubextensions.startProfileForTransaction(transaction);
      }
    }

    if (client && typeof client.on === 'function') {
      client.on('startTransaction', (transaction) => {
        if (utils.shouldProfileTransaction(transaction)) {
          hubextensions.startProfileForTransaction(transaction);
        }
      });

      client.on('beforeEnvelope', (envelope) => {
        // if not profiles are in queue, there is nothing to add to the envelope.
        if (!utils.getActiveProfilesCount()) {
          return;
        }

        const profiledTransactionEvents = utils.findProfiledTransactionsFromEnvelope(envelope);
        if (!profiledTransactionEvents.length) {
          return;
        }

        const profilesToAddToEnvelope = [];

        for (const profiledTransaction of profiledTransactionEvents) {
          const context = profiledTransaction && profiledTransaction.contexts;
          const profile_id = context && context['profile'] && context['profile']['profile_id'];
          const start_timestamp = context && context['profile'] && context['profile']['start_timestamp'];

          if (typeof profile_id !== 'string') {
            debugBuild.DEBUG_BUILD && utils$1.logger.log('[Profiling] cannot find profile for a transaction without a profile context');
            continue;
          }

          if (!profile_id) {
            debugBuild.DEBUG_BUILD && utils$1.logger.log('[Profiling] cannot find profile for a transaction without a profile context');
            continue;
          }

          // Remove the profile from the transaction context before sending, relay will take care of the rest.
          if (context && context['profile']) {
            delete context.profile;
          }

          const profile = utils.takeProfileFromGlobalCache(profile_id);
          if (!profile) {
            debugBuild.DEBUG_BUILD && utils$1.logger.log(`[Profiling] Could not retrieve profile for transaction: ${profile_id}`);
            continue;
          }

          const profileEvent = utils.createProfilingEvent(
            profile_id,
            start_timestamp ,
            profile,
            profiledTransaction ,
          );
          if (profileEvent) {
            profilesToAddToEnvelope.push(profileEvent);
          }
        }

        utils.addProfilesToEnvelope(envelope, profilesToAddToEnvelope);
      });
    } else {
      utils$1.logger.warn('[Profiling] Client does not support hooks, profiling will be disabled');
    }
  }
} BrowserProfilingIntegration.__initStatic();

exports.BrowserProfilingIntegration = BrowserProfilingIntegration;


},{"../debug-build.js":35,"./hubextensions.js":46,"./utils.js":48,"@sentry/utils":117}],48:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const helpers = require('../helpers.js');
require('../stack-parsers.js');
require('../sdk.js');
require('../integrations/globalhandlers.js');
require('../integrations/trycatch.js');
require('../integrations/breadcrumbs.js');
require('../integrations/linkederrors.js');
require('../integrations/httpcontext.js');
require('../integrations/dedupe.js');

/* eslint-disable max-lines */

const MS_TO_NS = 1e6;
// Use 0 as main thread id which is identical to threadId in node:worker_threads
// where main logs 0 and workers seem to log in increments of 1
const THREAD_ID_STRING = String(0);
const THREAD_NAME = 'main';

// Machine properties (eval only once)
let OS_PLATFORM = '';
let OS_PLATFORM_VERSION = '';
let OS_ARCH = '';
let OS_BROWSER = (helpers.WINDOW.navigator && helpers.WINDOW.navigator.userAgent) || '';
let OS_MODEL = '';
const OS_LOCALE =
  (helpers.WINDOW.navigator && helpers.WINDOW.navigator.language) ||
  (helpers.WINDOW.navigator && helpers.WINDOW.navigator.languages && helpers.WINDOW.navigator.languages[0]) ||
  '';

function isUserAgentData(data) {
  return typeof data === 'object' && data !== null && 'getHighEntropyValues' in data;
}

// @ts-expect-error userAgentData is not part of the navigator interface yet
const userAgentData = helpers.WINDOW.navigator && helpers.WINDOW.navigator.userAgentData;

if (isUserAgentData(userAgentData)) {
  userAgentData
    .getHighEntropyValues(['architecture', 'model', 'platform', 'platformVersion', 'fullVersionList'])
    .then((ua) => {
      OS_PLATFORM = ua.platform || '';
      OS_ARCH = ua.architecture || '';
      OS_MODEL = ua.model || '';
      OS_PLATFORM_VERSION = ua.platformVersion || '';

      if (ua.fullVersionList && ua.fullVersionList.length > 0) {
        const firstUa = ua.fullVersionList[ua.fullVersionList.length - 1];
        OS_BROWSER = `${firstUa.brand} ${firstUa.version}`;
      }
    })
    .catch(e => void e);
}

function isProcessedJSSelfProfile(profile) {
  return !('thread_metadata' in profile);
}

// Enriches the profile with threadId of the current thread.
// This is done in node as we seem to not be able to get the info from C native code.
/**
 *
 */
function enrichWithThreadInformation(profile) {
  if (!isProcessedJSSelfProfile(profile)) {
    return profile;
  }

  return convertJSSelfProfileToSampledFormat(profile);
}

// Profile is marked as optional because it is deleted from the metadata
// by the integration before the event is processed by other integrations.

function getTraceId(event) {
  const traceId = event && event.contexts && event.contexts['trace'] && event.contexts['trace']['trace_id'];
  // Log a warning if the profile has an invalid traceId (should be uuidv4).
  // All profiles and transactions are rejected if this is the case and we want to
  // warn users that this is happening if they enable debug flag
  if (typeof traceId === 'string' && traceId.length !== 32) {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log(`[Profiling] Invalid traceId: ${traceId} on profiled event`);
    }
  }
  if (typeof traceId !== 'string') {
    return '';
  }

  return traceId;
}
/**
 * Creates a profiling event envelope from a Sentry event. If profile does not pass
 * validation, returns null.
 * @param event
 * @param dsn
 * @param metadata
 * @param tunnel
 * @returns {EventEnvelope | null}
 */

/**
 * Creates a profiling event envelope from a Sentry event.
 */
function createProfilePayload(
  profile_id,
  start_timestamp,
  processed_profile,
  event,
) {
  if (event.type !== 'transaction') {
    // createProfilingEventEnvelope should only be called for transactions,
    // we type guard this behavior with isProfiledTransactionEvent.
    throw new TypeError('Profiling events may only be attached to transactions, this should never occur.');
  }

  if (processed_profile === undefined || processed_profile === null) {
    throw new TypeError(
      `Cannot construct profiling event envelope without a valid profile. Got ${processed_profile} instead.`,
    );
  }

  const traceId = getTraceId(event);
  const enrichedThreadProfile = enrichWithThreadInformation(processed_profile);
  const transactionStartMs = start_timestamp
    ? start_timestamp
    : typeof event.start_timestamp === 'number'
      ? event.start_timestamp * 1000
      : Date.now();
  const transactionEndMs = typeof event.timestamp === 'number' ? event.timestamp * 1000 : Date.now();

  const profile = {
    event_id: profile_id,
    timestamp: new Date(transactionStartMs).toISOString(),
    platform: 'javascript',
    version: '1',
    release: event.release || '',
    environment: event.environment || core.DEFAULT_ENVIRONMENT,
    runtime: {
      name: 'javascript',
      version: helpers.WINDOW.navigator.userAgent,
    },
    os: {
      name: OS_PLATFORM,
      version: OS_PLATFORM_VERSION,
      build_number: OS_BROWSER,
    },
    device: {
      locale: OS_LOCALE,
      model: OS_MODEL,
      manufacturer: OS_BROWSER,
      architecture: OS_ARCH,
      is_emulator: false,
    },
    debug_meta: {
      images: applyDebugMetadata(processed_profile.resources),
    },
    profile: enrichedThreadProfile,
    transactions: [
      {
        name: event.transaction || '',
        id: event.event_id || utils.uuid4(),
        trace_id: traceId,
        active_thread_id: THREAD_ID_STRING,
        relative_start_ns: '0',
        relative_end_ns: ((transactionEndMs - transactionStartMs) * 1e6).toFixed(0),
      },
    ],
  };

  return profile;
}

/*
  See packages/tracing-internal/src/browser/router.ts
*/
/**
 *
 */
function isAutomatedPageLoadTransaction(transaction) {
  return transaction.op === 'pageload';
}

/**
 * Converts a JSSelfProfile to a our sampled format.
 * Does not currently perform stack indexing.
 */
function convertJSSelfProfileToSampledFormat(input) {
  let EMPTY_STACK_ID = undefined;
  let STACK_ID = 0;

  // Initialize the profile that we will fill with data
  const profile = {
    samples: [],
    stacks: [],
    frames: [],
    thread_metadata: {
      [THREAD_ID_STRING]: { name: THREAD_NAME },
    },
  };

  if (!input.samples.length) {
    return profile;
  }

  // We assert samples.length > 0 above and timestamp should always be present
  const start = input.samples[0].timestamp;
  // The JS SDK might change it's time origin based on some heuristic (see See packages/utils/src/time.ts)
  // when that happens, we need to ensure we are correcting the profile timings so the two timelines stay in sync.
  // Since JS self profiling time origin is always initialized to performance.timeOrigin, we need to adjust for
  // the drift between the SDK selected value and our profile time origin.
  const origin =
    typeof performance.timeOrigin === 'number' ? performance.timeOrigin : utils.browserPerformanceTimeOrigin || 0;
  const adjustForOriginChange = origin - (utils.browserPerformanceTimeOrigin || origin);

  for (let i = 0; i < input.samples.length; i++) {
    const jsSample = input.samples[i];

    // If sample has no stack, add an empty sample
    if (jsSample.stackId === undefined) {
      if (EMPTY_STACK_ID === undefined) {
        EMPTY_STACK_ID = STACK_ID;
        profile.stacks[EMPTY_STACK_ID] = [];
        STACK_ID++;
      }

      profile['samples'][i] = {
        // convert ms timestamp to ns
        elapsed_since_start_ns: ((jsSample.timestamp + adjustForOriginChange - start) * MS_TO_NS).toFixed(0),
        stack_id: EMPTY_STACK_ID,
        thread_id: THREAD_ID_STRING,
      };
      continue;
    }

    let stackTop = input.stacks[jsSample.stackId];

    // Functions in top->down order (root is last)
    // We follow the stackTop.parentId trail and collect each visited frameId
    const stack = [];

    while (stackTop) {
      stack.push(stackTop.frameId);

      const frame = input.frames[stackTop.frameId];

      // If our frame has not been indexed yet, index it
      if (profile.frames[stackTop.frameId] === undefined) {
        profile.frames[stackTop.frameId] = {
          function: frame.name,
          abs_path: typeof frame.resourceId === 'number' ? input.resources[frame.resourceId] : undefined,
          lineno: frame.line,
          colno: frame.column,
        };
      }

      stackTop = stackTop.parentId === undefined ? undefined : input.stacks[stackTop.parentId];
    }

    const sample = {
      // convert ms timestamp to ns
      elapsed_since_start_ns: ((jsSample.timestamp + adjustForOriginChange - start) * MS_TO_NS).toFixed(0),
      stack_id: STACK_ID,
      thread_id: THREAD_ID_STRING,
    };

    profile['stacks'][STACK_ID] = stack;
    profile['samples'][i] = sample;
    STACK_ID++;
  }

  return profile;
}

/**
 * Adds items to envelope if they are not already present - mutates the envelope.
 * @param envelope
 */
function addProfilesToEnvelope(envelope, profiles) {
  if (!profiles.length) {
    return envelope;
  }

  for (const profile of profiles) {
    // @ts-expect-error untyped envelope
    envelope[1].push([{ type: 'profile' }, profile]);
  }
  return envelope;
}

/**
 * Finds transactions with profile_id context in the envelope
 * @param envelope
 * @returns
 */
function findProfiledTransactionsFromEnvelope(envelope) {
  const events = [];

  utils.forEachEnvelopeItem(envelope, (item, type) => {
    if (type !== 'transaction') {
      return;
    }

    for (let j = 1; j < item.length; j++) {
      const event = item[j] ;

      if (event && event.contexts && event.contexts['profile'] && event.contexts['profile']['profile_id']) {
        events.push(item[j] );
      }
    }
  });

  return events;
}

const debugIdStackParserCache = new WeakMap();
/**
 * Applies debug meta data to an event from a list of paths to resources (sourcemaps)
 */
function applyDebugMetadata(resource_paths) {
  const debugIdMap = utils.GLOBAL_OBJ._sentryDebugIds;

  if (!debugIdMap) {
    return [];
  }

  const hub = core.getCurrentHub();
  if (!hub) {
    return [];
  }
  const client = hub.getClient();
  if (!client) {
    return [];
  }
  const options = client.getOptions();
  if (!options) {
    return [];
  }
  const stackParser = options.stackParser;
  if (!stackParser) {
    return [];
  }

  let debugIdStackFramesCache;
  const cachedDebugIdStackFrameCache = debugIdStackParserCache.get(stackParser);
  if (cachedDebugIdStackFrameCache) {
    debugIdStackFramesCache = cachedDebugIdStackFrameCache;
  } else {
    debugIdStackFramesCache = new Map();
    debugIdStackParserCache.set(stackParser, debugIdStackFramesCache);
  }

  // Build a map of filename -> debug_id
  const filenameDebugIdMap = Object.keys(debugIdMap).reduce((acc, debugIdStackTrace) => {
    let parsedStack;

    const cachedParsedStack = debugIdStackFramesCache.get(debugIdStackTrace);
    if (cachedParsedStack) {
      parsedStack = cachedParsedStack;
    } else {
      parsedStack = stackParser(debugIdStackTrace);
      debugIdStackFramesCache.set(debugIdStackTrace, parsedStack);
    }

    for (let i = parsedStack.length - 1; i >= 0; i--) {
      const stackFrame = parsedStack[i];
      const file = stackFrame && stackFrame.filename;

      if (stackFrame && file) {
        acc[file] = debugIdMap[debugIdStackTrace] ;
        break;
      }
    }
    return acc;
  }, {});

  const images = [];
  for (const path of resource_paths) {
    if (path && filenameDebugIdMap[path]) {
      images.push({
        type: 'sourcemap',
        code_file: path,
        debug_id: filenameDebugIdMap[path] ,
      });
    }
  }

  return images;
}

/**
 * Checks the given sample rate to make sure it is valid type and value (a boolean, or a number between 0 and 1).
 */
function isValidSampleRate(rate) {
  // we need to check NaN explicitly because it's of type 'number' and therefore wouldn't get caught by this typecheck
  if ((typeof rate !== 'number' && typeof rate !== 'boolean') || (typeof rate === 'number' && isNaN(rate))) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.warn(
        `[Profiling] Invalid sample rate. Sample rate must be a boolean or a number between 0 and 1. Got ${JSON.stringify(
          rate,
        )} of type ${JSON.stringify(typeof rate)}.`,
      );
    return false;
  }

  // Boolean sample rates are always valid
  if (rate === true || rate === false) {
    return true;
  }

  // in case sampleRate is a boolean, it will get automatically cast to 1 if it's true and 0 if it's false
  if (rate < 0 || rate > 1) {
    debugBuild.DEBUG_BUILD && utils.logger.warn(`[Profiling] Invalid sample rate. Sample rate must be between 0 and 1. Got ${rate}.`);
    return false;
  }
  return true;
}

function isValidProfile(profile) {
  if (profile.samples.length < 2) {
    if (debugBuild.DEBUG_BUILD) {
      // Log a warning if the profile has less than 2 samples so users can know why
      // they are not seeing any profiling data and we cant avoid the back and forth
      // of asking them to provide us with a dump of the profile data.
      utils.logger.log('[Profiling] Discarding profile because it contains less than 2 samples');
    }
    return false;
  }

  if (!profile.frames.length) {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log('[Profiling] Discarding profile because it contains no frames');
    }
    return false;
  }

  return true;
}

// Keep a flag value to avoid re-initializing the profiler constructor. If it fails
// once, it will always fail and this allows us to early return.
let PROFILING_CONSTRUCTOR_FAILED = false;
const MAX_PROFILE_DURATION_MS = 30000;

/**
 * Check if profiler constructor is available.
 * @param maybeProfiler
 */
function isJSProfilerSupported(maybeProfiler) {
  return typeof maybeProfiler === 'function';
}

/**
 * Starts the profiler and returns the profiler instance.
 */
function startJSSelfProfile() {
  // Feature support check first
  const JSProfilerConstructor = helpers.WINDOW.Profiler;

  if (!isJSProfilerSupported(JSProfilerConstructor)) {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log(
        '[Profiling] Profiling is not supported by this browser, Profiler interface missing on window object.',
      );
    }
    return;
  }

  // From initial testing, it seems that the minimum value for sampleInterval is 10ms.
  const samplingIntervalMS = 10;
  // Start the profiler
  const maxSamples = Math.floor(MAX_PROFILE_DURATION_MS / samplingIntervalMS);

  // Attempt to initialize the profiler constructor, if it fails, we disable profiling for the current user session.
  // This is likely due to a missing 'Document-Policy': 'js-profiling' header. We do not want to throw an error if this happens
  // as we risk breaking the user's application, so just disable profiling and log an error.
  try {
    return new JSProfilerConstructor({ sampleInterval: samplingIntervalMS, maxBufferSize: maxSamples });
  } catch (e) {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log(
        "[Profiling] Failed to initialize the Profiling constructor, this is likely due to a missing 'Document-Policy': 'js-profiling' header.",
      );
      utils.logger.log('[Profiling] Disabling profiling for current user session.');
    }
    PROFILING_CONSTRUCTOR_FAILED = true;
  }

  return;
}

/**
 * Determine if a profile should be profiled.
 */
function shouldProfileTransaction(transaction) {
  // If constructor failed once, it will always fail, so we can early return.
  if (PROFILING_CONSTRUCTOR_FAILED) {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log('[Profiling] Profiling has been disabled for the duration of the current user session.');
    }
    return false;
  }

  if (!transaction.sampled) {
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.log('[Profiling] Discarding profile because transaction was not sampled.');
    }
    return false;
  }

  const client = core.getClient();
  const options = client && client.getOptions();
  if (!options) {
    debugBuild.DEBUG_BUILD && utils.logger.log('[Profiling] Profiling disabled, no options found.');
    return false;
  }

  // @ts-expect-error profilesSampleRate is not part of the browser options yet
  const profilesSampleRate = options.profilesSampleRate;

  // Since this is coming from the user (or from a function provided by the user), who knows what we might get. (The
  // only valid values are booleans or numbers between 0 and 1.)
  if (!isValidSampleRate(profilesSampleRate)) {
    debugBuild.DEBUG_BUILD && utils.logger.warn('[Profiling] Discarding profile because of invalid sample rate.');
    return false;
  }

  // if the function returned 0 (or false), or if `profileSampleRate` is 0, it's a sign the profile should be dropped
  if (!profilesSampleRate) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.log(
        '[Profiling] Discarding profile because a negative sampling decision was inherited or profileSampleRate is set to 0',
      );
    return false;
  }

  // Now we roll the dice. Math.random is inclusive of 0, but not of 1, so strict < is safe here. In case sampleRate is
  // a boolean, the < comparison will cause it to be automatically cast to 1 if it's true and 0 if it's false.
  const sampled = profilesSampleRate === true ? true : Math.random() < profilesSampleRate;
  // Check if we should sample this profile
  if (!sampled) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.log(
        `[Profiling] Discarding profile because it's not included in the random sample (sampling rate = ${Number(
          profilesSampleRate,
        )})`,
      );
    return false;
  }

  return true;
}

/**
 * Creates a profiling envelope item, if the profile does not pass validation, returns null.
 * @param event
 * @returns {Profile | null}
 */
function createProfilingEvent(
  profile_id,
  start_timestamp,
  profile,
  event,
) {
  if (!isValidProfile(profile)) {
    return null;
  }

  return createProfilePayload(profile_id, start_timestamp, profile, event);
}

const PROFILE_MAP = new Map();
/**
 *
 */
function getActiveProfilesCount() {
  return PROFILE_MAP.size;
}

/**
 * Retrieves profile from global cache and removes it.
 */
function takeProfileFromGlobalCache(profile_id) {
  const profile = PROFILE_MAP.get(profile_id);
  if (profile) {
    PROFILE_MAP.delete(profile_id);
  }
  return profile;
}
/**
 * Adds profile to global cache and evicts the oldest profile if the cache is full.
 */
function addProfileToGlobalCache(profile_id, profile) {
  PROFILE_MAP.set(profile_id, profile);

  if (PROFILE_MAP.size > 30) {
    const last = PROFILE_MAP.keys().next().value;
    PROFILE_MAP.delete(last);
  }
}

exports.MAX_PROFILE_DURATION_MS = MAX_PROFILE_DURATION_MS;
exports.addProfileToGlobalCache = addProfileToGlobalCache;
exports.addProfilesToEnvelope = addProfilesToEnvelope;
exports.applyDebugMetadata = applyDebugMetadata;
exports.convertJSSelfProfileToSampledFormat = convertJSSelfProfileToSampledFormat;
exports.createProfilePayload = createProfilePayload;
exports.createProfilingEvent = createProfilingEvent;
exports.enrichWithThreadInformation = enrichWithThreadInformation;
exports.findProfiledTransactionsFromEnvelope = findProfiledTransactionsFromEnvelope;
exports.getActiveProfilesCount = getActiveProfilesCount;
exports.isAutomatedPageLoadTransaction = isAutomatedPageLoadTransaction;
exports.isValidSampleRate = isValidSampleRate;
exports.shouldProfileTransaction = shouldProfileTransaction;
exports.startJSSelfProfile = startJSSelfProfile;
exports.takeProfileFromGlobalCache = takeProfileFromGlobalCache;


},{"../debug-build.js":35,"../helpers.js":37,"../integrations/breadcrumbs.js":39,"../integrations/dedupe.js":40,"../integrations/globalhandlers.js":41,"../integrations/httpcontext.js":42,"../integrations/linkederrors.js":44,"../integrations/trycatch.js":45,"../sdk.js":49,"../stack-parsers.js":50,"@sentry/core":65,"@sentry/utils":117}],49:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const client = require('./client.js');
const debugBuild = require('./debug-build.js');
const helpers = require('./helpers.js');
const globalhandlers = require('./integrations/globalhandlers.js');
const trycatch = require('./integrations/trycatch.js');
const breadcrumbs = require('./integrations/breadcrumbs.js');
const linkederrors = require('./integrations/linkederrors.js');
const httpcontext = require('./integrations/httpcontext.js');
const dedupe = require('./integrations/dedupe.js');
const stackParsers = require('./stack-parsers.js');
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
    debugBuild.DEBUG_BUILD && utils.logger.error('Global document not defined in showReportDialog call');
    return;
  }

  const { client, scope } = hub.getStackTop();
  const dsn = options.dsn || (client && client.getDsn());
  if (!dsn) {
    debugBuild.DEBUG_BUILD && utils.logger.error('DSN not configured for showReportDialog call');
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
  script.crossOrigin = 'anonymous';
  script.src = core.getReportDialogEndpoint(dsn, options);

  if (options.onLoad) {
    script.onload = options.onLoad;
  }

  const { onClose } = options;
  if (onClose) {
    const reportDialogClosedMessageHandler = (event) => {
      if (event.data === '__sentry_reportdialog_closed__') {
        try {
          onClose();
        } finally {
          helpers.WINDOW.removeEventListener('message', reportDialogClosedMessageHandler);
        }
      }
    };
    helpers.WINDOW.addEventListener('message', reportDialogClosedMessageHandler);
  }

  const injectionPoint = helpers.WINDOW.document.head || helpers.WINDOW.document.body;
  if (injectionPoint) {
    injectionPoint.appendChild(script);
  } else {
    debugBuild.DEBUG_BUILD && utils.logger.error('Not injecting report dialog. No injection point found in HTML');
  }
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
 * Wrap code within a try/catch block so the SDK is able to capture errors.
 *
 * @deprecated This function will be removed in v8.
 * It is not part of Sentry's official API and it's easily replaceable by using a try/catch block
 * and calling Sentry.captureException.
 *
 * @param fn A function to wrap.
 *
 * @returns The result of wrapped function call.
 */
// TODO(v8): Remove this function
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
    debugBuild.DEBUG_BUILD && utils.logger.warn('Session tracking in non-browser environment with @sentry/browser is not supported.');
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
  utils.addHistoryInstrumentationHandler(({ from, to }) => {
    // Don't create an additional session for the initial route or if the location did not change
    if (from !== undefined && from !== to) {
      startSessionOnHub(core.getCurrentHub());
    }
  });
}

/**
 * Captures user feedback and sends it to Sentry.
 */
function captureUserFeedback(feedback) {
  const client = core.getClient();
  if (client) {
    client.captureUserFeedback(feedback);
  }
}

exports.captureUserFeedback = captureUserFeedback;
exports.defaultIntegrations = defaultIntegrations;
exports.forceLoad = forceLoad;
exports.init = init;
exports.onLoad = onLoad;
exports.showReportDialog = showReportDialog;
exports.wrap = wrap;


},{"./client.js":34,"./debug-build.js":35,"./helpers.js":37,"./integrations/breadcrumbs.js":39,"./integrations/dedupe.js":40,"./integrations/globalhandlers.js":41,"./integrations/httpcontext.js":42,"./integrations/linkederrors.js":44,"./integrations/trycatch.js":45,"./stack-parsers.js":50,"./transports/fetch.js":51,"./transports/xhr.js":54,"@sentry/core":65,"@sentry/utils":117}],50:[function(require,module,exports){
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
    in_app: true, // All browser frames are considered in_app
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
  /^\s*at (?:(.+?\)(?: \[.+\])?|.*?) ?\((?:address at )?)?(?:async )?((?:<anonymous>|[-a-z]+:|.*bundle|\/)?.*?)(?::(\d+))?(?::(\d+))?\)?\s*$/i;
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
  /^\s*(.*?)(?:\((.*?)\))?(?:^|@)?((?:[-a-z]+)?:\/.*?|\[native code\]|[^@]*(?:bundle|\d+\.js)|\/[\w\-. /=]+)(?::(\d+))?(?::(\d+))?\s*$/i;
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

const winjsRegex = /^\s*at (?:((?:\[object object\])?.+) )?\(?((?:[-a-z]+):.*?):(\d+)(?::(\d+))?\)?\s*$/i;

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


},{"@sentry/utils":117}],51:[function(require,module,exports){
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
  let pendingBodySize = 0;
  let pendingCount = 0;

  function makeRequest(request) {
    const requestSize = request.body.length;
    pendingBodySize += requestSize;
    pendingCount++;

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
      // - As per spec (https://fetch.spec.whatwg.org/#http-network-or-cache-fetch):
      //   If the sum of contentLength and inflightKeepaliveBytes is greater than 64 kibibytes, then return a network error.
      //   We will therefore only activate the flag when we're below that limit.
      // There is also a limit of requests that can be open at the same time, so we also limit this to 15
      // See https://github.com/getsentry/sentry-javascript/pull/7553 for details
      keepalive: pendingBodySize <= 60000 && pendingCount < 15,
      ...options.fetchOptions,
    };

    try {
      return nativeFetch(options.url, requestOptions).then(response => {
        pendingBodySize -= requestSize;
        pendingCount--;
        return {
          statusCode: response.status,
          headers: {
            'x-sentry-rate-limits': response.headers.get('X-Sentry-Rate-Limits'),
            'retry-after': response.headers.get('Retry-After'),
          },
        };
      });
    } catch (e) {
      utils.clearCachedFetchImplementation();
      pendingBodySize -= requestSize;
      pendingCount--;
      return utils$1.rejectedSyncPromise(e);
    }
  }

  return core.createTransport(options, makeRequest);
}

exports.makeFetchTransport = makeFetchTransport;


},{"./utils.js":53,"@sentry/core":65,"@sentry/utils":117}],52:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');

// 'Store', 'promisifyRequest' and 'createStore' were originally copied from the 'idb-keyval' package before being
// modified and simplified: https://github.com/jakearchibald/idb-keyval
//
// At commit: 0420a704fd6cbb4225429c536b1f61112d012fca
// Original licence:

// Copyright 2016, Jake Archibald
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//   http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

function promisifyRequest(request) {
  return new Promise((resolve, reject) => {
    // @ts-expect-error - file size hacks
    request.oncomplete = request.onsuccess = () => resolve(request.result);
    // @ts-expect-error - file size hacks
    request.onabort = request.onerror = () => reject(request.error);
  });
}

/** Create or open an IndexedDb store */
function createStore(dbName, storeName) {
  const request = indexedDB.open(dbName);
  request.onupgradeneeded = () => request.result.createObjectStore(storeName);
  const dbp = promisifyRequest(request);

  return callback => dbp.then(db => callback(db.transaction(storeName, 'readwrite').objectStore(storeName)));
}

function keys(store) {
  return promisifyRequest(store.getAllKeys() );
}

/** Insert into the store */
function insert(store, value, maxQueueSize) {
  return store(store => {
    return keys(store).then(keys => {
      if (keys.length >= maxQueueSize) {
        return;
      }

      // We insert with an incremented key so that the entries are popped in order
      store.put(value, Math.max(...keys, 0) + 1);
      return promisifyRequest(store.transaction);
    });
  });
}

/** Pop the oldest value from the store */
function pop(store) {
  return store(store => {
    return keys(store).then(keys => {
      if (keys.length === 0) {
        return undefined;
      }

      return promisifyRequest(store.get(keys[0])).then(value => {
        store.delete(keys[0]);
        return promisifyRequest(store.transaction).then(() => value);
      });
    });
  });
}

function createIndexedDbStore(options) {
  let store;

  // Lazily create the store only when it's needed
  function getStore() {
    if (store == undefined) {
      store = createStore(options.dbName || 'sentry-offline', options.storeName || 'queue');
    }

    return store;
  }

  return {
    insert: async (env) => {
      try {
        const serialized = await utils.serializeEnvelope(env, options.textEncoder);
        await insert(getStore(), serialized, options.maxQueueSize || 30);
      } catch (_) {
        //
      }
    },
    pop: async () => {
      try {
        const deserialized = await pop(getStore());
        if (deserialized) {
          return utils.parseEnvelope(
            deserialized,
            options.textEncoder || new TextEncoder(),
            options.textDecoder || new TextDecoder(),
          );
        }
      } catch (_) {
        //
      }

      return undefined;
    },
  };
}

function makeIndexedDbOfflineTransport(
  createTransport,
) {
  return options => createTransport({ ...options, createStore: createIndexedDbStore });
}

/**
 * Creates a transport that uses IndexedDb to store events when offline.
 */
function makeBrowserOfflineTransport(
  createTransport,
) {
  return makeIndexedDbOfflineTransport(core.makeOfflineTransport(createTransport));
}

exports.createStore = createStore;
exports.insert = insert;
exports.makeBrowserOfflineTransport = makeBrowserOfflineTransport;
exports.pop = pop;


},{"@sentry/core":65,"@sentry/utils":117}],53:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
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
      debugBuild.DEBUG_BUILD && utils.logger.warn('Could not create sandbox iframe for pure fetch check, bailing to window.fetch: ', e);
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


},{"../debug-build.js":35,"../helpers.js":37,"@sentry/utils":117}],54:[function(require,module,exports){
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


},{"@sentry/core":65,"@sentry/utils":117}],55:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

/**
 * Creates an envelope from a user feedback.
 */
function createUserFeedbackEnvelope(
  feedback,
  {
    metadata,
    tunnel,
    dsn,
  }

,
) {
  const headers = {
    event_id: feedback.event_id,
    sent_at: new Date().toISOString(),
    ...(metadata &&
      metadata.sdk && {
        sdk: {
          name: metadata.sdk.name,
          version: metadata.sdk.version,
        },
      }),
    ...(!!tunnel && !!dsn && { dsn: utils.dsnToString(dsn) }),
  };
  const item = createUserFeedbackEnvelopeItem(feedback);

  return utils.createEnvelope(headers, [item]);
}

function createUserFeedbackEnvelopeItem(feedback) {
  const feedbackHeaders = {
    type: 'user_report',
  };
  return [feedbackHeaders, feedback];
}

exports.createUserFeedbackEnvelope = createUserFeedbackEnvelope;


},{"@sentry/utils":117}],56:[function(require,module,exports){
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
  if (!dsn) {
    return '';
  }

  const endpoint = `${getBaseApiEndpoint(dsn)}embed/error-page/`;

  let encodedOptions = `dsn=${utils.dsnToString(dsn)}`;
  for (const key in dialogOptions) {
    if (key === 'dsn') {
      continue;
    }

    if (key === 'onClose') {
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


},{"@sentry/utils":117}],57:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const api = require('./api.js');
const debugBuild = require('./debug-build.js');
const envelope = require('./envelope.js');
const hub = require('./hub.js');
const integration = require('./integration.js');
const session = require('./session.js');
const dynamicSamplingContext = require('./tracing/dynamicSamplingContext.js');
const prepareEvent = require('./utils/prepareEvent.js');

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

  /** Indicates whether this client's integrations have been set up. */

  /** Number of calls being processed */

  /** Holds flushable  */

  // eslint-disable-next-line @typescript-eslint/ban-types

  /**
   * Initializes this client instance.
   *
   * @param options Options for the client.
   */
   constructor(options) {
    this._options = options;
    this._integrations = {};
    this._integrationsInitialized = false;
    this._numProcessing = 0;
    this._outcomes = {};
    this._hooks = {};
    this._eventProcessors = [];

    if (options.dsn) {
      this._dsn = utils.makeDsn(options.dsn);
    } else {
      debugBuild.DEBUG_BUILD && utils.logger.warn('No DSN provided, client will not send events.');
    }

    if (this._dsn) {
      const url = api.getEnvelopeEndpointWithUrlEncodedAuth(this._dsn, options);
      this._transport = options.transport({
        recordDroppedEvent: this.recordDroppedEvent.bind(this),
        ...options.transportOptions,
        url,
      });
    }
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
   captureException(exception, hint, scope) {
    // ensure we haven't captured this very object before
    if (utils.checkOrSetAlreadyCaught(exception)) {
      debugBuild.DEBUG_BUILD && utils.logger.log(ALREADY_SEEN_ERROR);
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
      debugBuild.DEBUG_BUILD && utils.logger.log(ALREADY_SEEN_ERROR);
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
    if (!(typeof session$1.release === 'string')) {
      debugBuild.DEBUG_BUILD && utils.logger.warn('Discarded session because of missing or non-string release');
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
   * @see SdkMetadata in @sentry/types
   *
   * @return The metadata of the SDK
   */
   getSdkMetadata() {
    return this._options._metadata;
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

  /** Get all installed event processors. */
   getEventProcessors() {
    return this._eventProcessors;
  }

  /** @inheritDoc */
   addEventProcessor(eventProcessor) {
    this._eventProcessors.push(eventProcessor);
  }

  /**
   * Sets up the integrations
   */
   setupIntegrations(forceInitialize) {
    if ((forceInitialize && !this._integrationsInitialized) || (this._isEnabled() && !this._integrationsInitialized)) {
      this._integrations = integration.setupIntegrations(this, this._options.integrations);
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
      debugBuild.DEBUG_BUILD && utils.logger.warn(`Cannot retrieve integration ${integration.id} from the current Client`);
      return null;
    }
  }

  /**
   * @inheritDoc
   */
   addIntegration(integration$1) {
    integration.setupIntegration(this, integration$1, this._integrations);
  }

  /**
   * @inheritDoc
   */
   sendEvent(event, hint = {}) {
    this.emit('beforeSendEvent', event, hint);

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

    const promise = this._sendEnvelope(env);
    if (promise) {
      promise.then(sendResponse => this.emit('afterSendEvent', event, sendResponse), null);
    }
  }

  /**
   * @inheritDoc
   */
   sendSession(session) {
    const env = envelope.createSessionEnvelope(session, this._dsn, this._options._metadata, this._options.tunnel);
    void this._sendEnvelope(env);
  }

  /**
   * @inheritDoc
   */
   recordDroppedEvent(reason, category, _event) {
    // Note: we use `event` in replay, where we overwrite this hook.

    if (this._options.sendClientReports) {
      // We want to track each category (error, transaction, session, replay_event) separately
      // but still keep the distinction between different type of outcomes.
      // We could use nested maps, but it's much easier to read and type this way.
      // A correct type for map-based implementation if we want to go that route
      // would be `Partial<Record<SentryRequestType, Partial<Record<Outcome, number>>>>`
      // With typescript 4.1 we could even use template literal types
      const key = `${reason}:${category}`;
      debugBuild.DEBUG_BUILD && utils.logger.log(`Adding outcome: "${key}"`);

      // The following works because undefined + 1 === NaN and NaN is falsy
      this._outcomes[key] = this._outcomes[key] + 1 || 1;
    }
  }

  // Keep on() & emit() signatures in sync with types' client.ts interface
  /* eslint-disable @typescript-eslint/unified-signatures */

  /** @inheritdoc */

  /** @inheritdoc */
   on(hook, callback) {
    if (!this._hooks[hook]) {
      this._hooks[hook] = [];
    }

    // @ts-expect-error We assue the types are correct
    this._hooks[hook].push(callback);
  }

  /** @inheritdoc */

  /** @inheritdoc */
   emit(hook, ...rest) {
    if (this._hooks[hook]) {
      this._hooks[hook].forEach(callback => callback(...rest));
    }
  }

  /* eslint-enable @typescript-eslint/unified-signatures */

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

  /** Determines whether this SDK is enabled and a transport is present. */
   _isEnabled() {
    return this.getOptions().enabled !== false && this._transport !== undefined;
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
   _prepareEvent(event, hint, scope) {
    const options = this.getOptions();
    const integrations = Object.keys(this._integrations);
    if (!hint.integrations && integrations.length > 0) {
      hint.integrations = integrations;
    }

    this.emit('preprocessEvent', event, hint);

    return prepareEvent.prepareEvent(options, event, hint, scope, this).then(evt => {
      if (evt === null) {
        return evt;
      }

      // If a trace context is not set on the event, we use the propagationContext set on the event to
      // generate a trace context. If the propagationContext does not have a dynamic sampling context, we
      // also generate one for it.
      const { propagationContext } = evt.sdkProcessingMetadata || {};
      const trace = evt.contexts && evt.contexts.trace;
      if (!trace && propagationContext) {
        const { traceId: trace_id, spanId, parentSpanId, dsc } = propagationContext ;
        evt.contexts = {
          trace: {
            trace_id,
            span_id: spanId,
            parent_span_id: parentSpanId,
          },
          ...evt.contexts,
        };

        const dynamicSamplingContext$1 = dsc ? dsc : dynamicSamplingContext.getDynamicSamplingContextFromClient(trace_id, this, scope);

        evt.sdkProcessingMetadata = {
          dynamicSamplingContext: dynamicSamplingContext$1,
          ...evt.sdkProcessingMetadata,
        };
      }
      return evt;
    });
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
        if (debugBuild.DEBUG_BUILD) {
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

    const dataCategory = eventType === 'replay_event' ? 'replay' : eventType;

    return this._prepareEvent(event, hint, scope)
      .then(prepared => {
        if (prepared === null) {
          this.recordDroppedEvent('event_processor', dataCategory, event);
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
          this.recordDroppedEvent('before_send', dataCategory, event);
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
          originalException: reason,
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
    this.emit('beforeEnvelope', envelope);

    if (this._isEnabled() && this._transport) {
      return this._transport.send(envelope).then(null, reason => {
        debugBuild.DEBUG_BUILD && utils.logger.error('Error while sending event:', reason);
      });
    } else {
      debugBuild.DEBUG_BUILD && utils.logger.error('Transport disabled');
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

/**
 * Add an event processor to the current client.
 * This event processor will run for all events processed by this client.
 */
function addEventProcessor(callback) {
  const client = hub.getCurrentHub().getClient();

  if (!client || !client.addEventProcessor) {
    return;
  }

  client.addEventProcessor(callback);
}

exports.BaseClient = BaseClient;
exports.addEventProcessor = addEventProcessor;


},{"./api.js":56,"./debug-build.js":60,"./envelope.js":61,"./hub.js":64,"./integration.js":66,"./session.js":77,"./tracing/dynamicSamplingContext.js":79,"./utils/prepareEvent.js":95,"@sentry/utils":117}],58:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

/**
 * Create envelope from check in item.
 */
function createCheckInEnvelope(
  checkIn,
  dynamicSamplingContext,
  metadata,
  tunnel,
  dsn,
) {
  const headers = {
    sent_at: new Date().toISOString(),
  };

  if (metadata && metadata.sdk) {
    headers.sdk = {
      name: metadata.sdk.name,
      version: metadata.sdk.version,
    };
  }

  if (!!tunnel && !!dsn) {
    headers.dsn = utils.dsnToString(dsn);
  }

  if (dynamicSamplingContext) {
    headers.trace = utils.dropUndefinedKeys(dynamicSamplingContext) ;
  }

  const item = createCheckInEnvelopeItem(checkIn);
  return utils.createEnvelope(headers, [item]);
}

function createCheckInEnvelopeItem(checkIn) {
  const checkInHeaders = {
    type: 'check_in',
  };
  return [checkInHeaders, checkIn];
}

exports.createCheckInEnvelope = createCheckInEnvelope;


},{"@sentry/utils":117}],59:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const DEFAULT_ENVIRONMENT = 'production';

exports.DEFAULT_ENVIRONMENT = DEFAULT_ENVIRONMENT;


},{}],60:[function(require,module,exports){
arguments[4][21][0].apply(exports,arguments)
},{"dup":21}],61:[function(require,module,exports){
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
    ...(!!tunnel && dsn && { dsn: utils.dsnToString(dsn) }),
  };

  const envelopeItem =
    'aggregates' in session ? [{ type: 'sessions' }, session] : [{ type: 'session' }, session.toJSON()];

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

  /*
    Note: Due to TS, event.type may be `replay_event`, theoretically.
    In practice, we never call `createEventEnvelope` with `replay_event` type,
    and we'd have to adjut a looot of types to make this work properly.
    We want to avoid casting this around, as that could lead to bugs (e.g. when we add another type)
    So the safe choice is to really guard against the replay_event type here.
  */
  const eventType = event.type && event.type !== 'replay_event' ? event.type : 'event';

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


},{"@sentry/utils":117}],62:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('./debug-build.js');

/**
 * Returns the global event processors.
 * @deprecated Global event processors will be removed in v8.
 */
function getGlobalEventProcessors() {
  return utils.getGlobalSingleton('globalEventProcessors', () => []);
}

/**
 * Add a EventProcessor to be kept globally.
 * @deprecated Use `addEventProcessor` instead. Global event processors will be removed in v8.
 */
function addGlobalEventProcessor(callback) {
  // eslint-disable-next-line deprecation/deprecation
  getGlobalEventProcessors().push(callback);
}

/**
 * Process an array of event processors, returning the processed event (or `null` if the event was dropped).
 */
function notifyEventProcessors(
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

      debugBuild.DEBUG_BUILD && processor.id && result === null && utils.logger.log(`Event processor "${processor.id}" dropped event`);

      if (utils.isThenable(result)) {
        void result
          .then(final => notifyEventProcessors(processors, final, hint, index + 1).then(resolve))
          .then(null, reject);
      } else {
        void notifyEventProcessors(processors, result, hint, index + 1)
          .then(resolve)
          .then(null, reject);
      }
    }
  });
}

exports.addGlobalEventProcessor = addGlobalEventProcessor;
exports.getGlobalEventProcessors = getGlobalEventProcessors;
exports.notifyEventProcessors = notifyEventProcessors;


},{"./debug-build.js":60,"@sentry/utils":117}],63:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('./debug-build.js');
const hub = require('./hub.js');
const prepareEvent = require('./utils/prepareEvent.js');

// Note: All functions in this file are typed with a return value of `ReturnType<Hub[HUB_FUNCTION]>`,
// where HUB_FUNCTION is some method on the Hub class.
//
// This is done to make sure the top level SDK methods stay in sync with the hub methods.
// Although every method here has an explicit return type, some of them (that map to void returns) do not
// contain `return` keywords. This is done to save on bundle size, as `return` is not minifiable.

/**
 * Captures an exception event and sends it to Sentry.
 * This accepts an event hint as optional second parameter.
 * Alternatively, you can also pass a CaptureContext directly as second parameter.
 */
function captureException(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  exception,
  hint,
) {
  return hub.getCurrentHub().captureException(exception, prepareEvent.parseEventHintOrCaptureContext(hint));
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

/**
 * Create a cron monitor check in and send it to Sentry.
 *
 * @param checkIn An object that describes a check in.
 * @param upsertMonitorConfig An optional object that describes a monitor config. Use this if you want
 * to create a monitor automatically when sending a check in.
 */
function captureCheckIn(checkIn, upsertMonitorConfig) {
  const hub$1 = hub.getCurrentHub();
  const scope = hub$1.getScope();
  const client = hub$1.getClient();
  if (!client) {
    debugBuild.DEBUG_BUILD && utils.logger.warn('Cannot capture check-in. No client defined.');
  } else if (!client.captureCheckIn) {
    debugBuild.DEBUG_BUILD && utils.logger.warn('Cannot capture check-in. Client does not support sending check-ins.');
  } else {
    return client.captureCheckIn(checkIn, upsertMonitorConfig, scope);
  }

  return utils.uuid4();
}

/**
 * Wraps a callback with a cron monitor check in. The check in will be sent to Sentry when the callback finishes.
 *
 * @param monitorSlug The distinct slug of the monitor.
 * @param upsertMonitorConfig An optional object that describes a monitor config. Use this if you want
 * to create a monitor automatically when sending a check in.
 */
function withMonitor(
  monitorSlug,
  callback,
  upsertMonitorConfig,
) {
  const checkInId = captureCheckIn({ monitorSlug, status: 'in_progress' }, upsertMonitorConfig);
  const now = utils.timestampInSeconds();

  function finishCheckIn(status) {
    captureCheckIn({ monitorSlug, status, checkInId, duration: utils.timestampInSeconds() - now });
  }

  let maybePromiseResult;
  try {
    maybePromiseResult = callback();
  } catch (e) {
    finishCheckIn('error');
    throw e;
  }

  if (utils.isThenable(maybePromiseResult)) {
    Promise.resolve(maybePromiseResult).then(
      () => {
        finishCheckIn('ok');
      },
      () => {
        finishCheckIn('error');
      },
    );
  } else {
    finishCheckIn('ok');
  }

  return maybePromiseResult;
}

/**
 * Call `flush()` on the current client, if there is one. See {@link Client.flush}.
 *
 * @param timeout Maximum time in ms the client should wait to flush its event queue. Omitting this parameter will cause
 * the client to wait until all events are sent before resolving the promise.
 * @returns A promise which resolves to `true` if the queue successfully drains before the timeout, or `false` if it
 * doesn't (or if there's no client defined).
 */
async function flush(timeout) {
  const client = getClient();
  if (client) {
    return client.flush(timeout);
  }
  debugBuild.DEBUG_BUILD && utils.logger.warn('Cannot flush events. No client defined.');
  return Promise.resolve(false);
}

/**
 * Call `close()` on the current client, if there is one. See {@link Client.close}.
 *
 * @param timeout Maximum time in ms the client should wait to flush its event queue before shutting down. Omitting this
 * parameter will cause the client to wait until all events are sent before disabling itself.
 * @returns A promise which resolves to `true` if the queue successfully drains before the timeout, or `false` if it
 * doesn't (or if there's no client defined).
 */
async function close(timeout) {
  const client = getClient();
  if (client) {
    return client.close(timeout);
  }
  debugBuild.DEBUG_BUILD && utils.logger.warn('Cannot flush events and disable SDK. No client defined.');
  return Promise.resolve(false);
}

/**
 * This is the getter for lastEventId.
 *
 * @returns The last event id of a captured event.
 */
function lastEventId() {
  return hub.getCurrentHub().lastEventId();
}

/**
 * Get the currently active client.
 */
function getClient() {
  return hub.getCurrentHub().getClient();
}

exports.addBreadcrumb = addBreadcrumb;
exports.captureCheckIn = captureCheckIn;
exports.captureEvent = captureEvent;
exports.captureException = captureException;
exports.captureMessage = captureMessage;
exports.close = close;
exports.configureScope = configureScope;
exports.flush = flush;
exports.getClient = getClient;
exports.lastEventId = lastEventId;
exports.setContext = setContext;
exports.setExtra = setExtra;
exports.setExtras = setExtras;
exports.setTag = setTag;
exports.setTags = setTags;
exports.setUser = setUser;
exports.startTransaction = startTransaction;
exports.withMonitor = withMonitor;
exports.withScope = withScope;


},{"./debug-build.js":60,"./hub.js":64,"./utils/prepareEvent.js":95,"@sentry/utils":117}],64:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const constants = require('./constants.js');
const debugBuild = require('./debug-build.js');
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
 * @inheritDoc
 */
class Hub  {
  /** Is a {@link Layer}[] containing the client and scope */

  /** Contains the last event id of a captured event.  */

  /**
   * Creates a new instance of the hub, will push one {@link Layer} into the
   * internal stack on creation.
   *
   * @param client bound to the hub.
   * @param scope bound to the hub.
   * @param version number, higher number means higher priority.
   */
   constructor(client, scope$1 = new scope.Scope(),   _version = API_VERSION) {this._version = _version;
    this._stack = [{ scope: scope$1 }];
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
    if (!event.type) {
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

    if (!client) return;

    const { beforeBreadcrumb = null, maxBreadcrumbs = DEFAULT_BREADCRUMBS } =
      (client.getOptions && client.getOptions()) || {};

    if (maxBreadcrumbs <= 0) return;

    const timestamp = utils.dateTimestampInSeconds();
    const mergedBreadcrumb = { timestamp, ...breadcrumb };
    const finalBreadcrumb = beforeBreadcrumb
      ? (utils.consoleSandbox(() => beforeBreadcrumb(mergedBreadcrumb, hint)) )
      : mergedBreadcrumb;

    if (finalBreadcrumb === null) return;

    if (client.emit) {
      client.emit('beforeAddBreadcrumb', finalBreadcrumb, hint);
    }

    scope.addBreadcrumb(finalBreadcrumb, maxBreadcrumbs);
  }

  /**
   * @inheritDoc
   */
   setUser(user) {
    this.getScope().setUser(user);
  }

  /**
   * @inheritDoc
   */
   setTags(tags) {
    this.getScope().setTags(tags);
  }

  /**
   * @inheritDoc
   */
   setExtras(extras) {
    this.getScope().setExtras(extras);
  }

  /**
   * @inheritDoc
   */
   setTag(key, value) {
    this.getScope().setTag(key, value);
  }

  /**
   * @inheritDoc
   */
   setExtra(key, extra) {
    this.getScope().setExtra(key, extra);
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
   setContext(name, context) {
    this.getScope().setContext(name, context);
  }

  /**
   * @inheritDoc
   */
   configureScope(callback) {
    const { scope, client } = this.getStackTop();
    if (client) {
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
      debugBuild.DEBUG_BUILD && utils.logger.warn(`Cannot retrieve integration ${integration.id} from the current Hub`);
      return null;
    }
  }

  /**
   * @inheritDoc
   */
   startTransaction(context, customSamplingContext) {
    const result = this._callExtensionMethod('startTransaction', context, customSamplingContext);

    if (debugBuild.DEBUG_BUILD && !result) {
      const client = this.getClient();
      if (!client) {
        utils.logger.warn(
          "Tracing extension 'startTransaction' is missing. You should 'init' the SDK before calling 'startTransaction'",
        );
      } else {
        utils.logger.warn(`Tracing extension 'startTransaction' has not been added. Call 'addTracingExtensions' before calling 'init':
Sentry.addTracingExtensions();
Sentry.init({...});
`);
      }
    }

    return result;
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
    const scope = layer.scope;
    const session$1 = scope.getSession();
    if (session$1) {
      session.closeSession(session$1);
    }
    this._sendSessionUpdate();

    // the session is over; take it off of the scope
    scope.setSession();
  }

  /**
   * @inheritDoc
   */
   startSession(context) {
    const { scope, client } = this.getStackTop();
    const { release, environment = constants.DEFAULT_ENVIRONMENT } = (client && client.getOptions()) || {};

    // Will fetch userAgent if called from browser sdk
    const { userAgent } = utils.GLOBAL_OBJ.navigator || {};

    const session$1 = session.makeSession({
      release,
      environment,
      user: scope.getUser(),
      ...(userAgent && { userAgent }),
      ...context,
    });

    // End existing session if there's one
    const currentSession = scope.getSession && scope.getSession();
    if (currentSession && currentSession.status === 'ok') {
      session.updateSession(currentSession, { status: 'exited' });
    }
    this.endSession();

    // Afterwards we set the new session on the scope
    scope.setSession(session$1);

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

    const session = scope.getSession();
    if (session && client && client.captureSession) {
      client.captureSession(session);
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
  // @ts-expect-error Function lacks ending return statement and return type does not include 'undefined'. ts(2366)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
   _callExtensionMethod(method, ...args) {
    const carrier = getMainCarrier();
    const sentry = carrier.__SENTRY__;
    if (sentry && sentry.extensions && typeof sentry.extensions[method] === 'function') {
      return sentry.extensions[method].apply(this, args);
    }
    debugBuild.DEBUG_BUILD && utils.logger.warn(`Extension method ${method} couldn't be found, doing nothing.`);
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

  if (registry.__SENTRY__ && registry.__SENTRY__.acs) {
    const hub = registry.__SENTRY__.acs.getCurrentHub();

    if (hub) {
      return hub;
    }
  }

  // Return hub that lives on a global object
  return getGlobalHub(registry);
}

function getGlobalHub(registry = getMainCarrier()) {
  // If there's no hub, or its an old API, assign a new one
  if (!hasHubOnCarrier(registry) || getHubFromCarrier(registry).isOlderThan(API_VERSION)) {
    setHubOnCarrier(registry, new Hub());
  }

  // Return hub that lives on a global object
  return getHubFromCarrier(registry);
}

/**
 * @private Private API with no semver guarantees!
 *
 * If the carrier does not contain a hub, a new hub is created with the global hub client and scope.
 */
function ensureHubOnCarrier(carrier, parent = getGlobalHub()) {
  // If there's no hub on current domain, or it's an old API, assign a new one
  if (!hasHubOnCarrier(carrier) || getHubFromCarrier(carrier).isOlderThan(API_VERSION)) {
    const globalHubTopStack = parent.getStackTop();
    setHubOnCarrier(carrier, new Hub(globalHubTopStack.client, scope.Scope.clone(globalHubTopStack.scope)));
  }
}

/**
 * @private Private API with no semver guarantees!
 *
 * Sets the global async context strategy
 */
function setAsyncContextStrategy(strategy) {
  // Get main carrier (global for every environment)
  const registry = getMainCarrier();
  registry.__SENTRY__ = registry.__SENTRY__ || {};
  registry.__SENTRY__.acs = strategy;
}

/**
 * Runs the supplied callback in its own async context. Async Context strategies are defined per SDK.
 *
 * @param callback The callback to run in its own async context
 * @param options Options to pass to the async context strategy
 * @returns The result of the callback
 */
function runWithAsyncContext(callback, options = {}) {
  const registry = getMainCarrier();

  if (registry.__SENTRY__ && registry.__SENTRY__.acs) {
    return registry.__SENTRY__.acs.runWithAsyncContext(callback, options);
  }

  // if there was no strategy, fallback to just calling the callback
  return callback();
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
exports.ensureHubOnCarrier = ensureHubOnCarrier;
exports.getCurrentHub = getCurrentHub;
exports.getHubFromCarrier = getHubFromCarrier;
exports.getMainCarrier = getMainCarrier;
exports.makeMain = makeMain;
exports.runWithAsyncContext = runWithAsyncContext;
exports.setAsyncContextStrategy = setAsyncContextStrategy;
exports.setHubOnCarrier = setHubOnCarrier;


},{"./constants.js":59,"./debug-build.js":60,"./scope.js":74,"./session.js":77,"@sentry/utils":117}],65:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const hubextensions = require('./tracing/hubextensions.js');
const idletransaction = require('./tracing/idletransaction.js');
const span = require('./tracing/span.js');
const transaction = require('./tracing/transaction.js');
const utils = require('./tracing/utils.js');
const spanstatus = require('./tracing/spanstatus.js');
const trace = require('./tracing/trace.js');
const dynamicSamplingContext = require('./tracing/dynamicSamplingContext.js');
const measurement = require('./tracing/measurement.js');
const envelope = require('./envelope.js');
const exports$1 = require('./exports.js');
const hub = require('./hub.js');
const session = require('./session.js');
const sessionflusher = require('./sessionflusher.js');
const scope = require('./scope.js');
const eventProcessors = require('./eventProcessors.js');
const api = require('./api.js');
const baseclient = require('./baseclient.js');
const serverRuntimeClient = require('./server-runtime-client.js');
const sdk = require('./sdk.js');
const base = require('./transports/base.js');
const offline = require('./transports/offline.js');
const multiplexed = require('./transports/multiplexed.js');
const version = require('./version.js');
const integration = require('./integration.js');
const index = require('./integrations/index.js');
const prepareEvent = require('./utils/prepareEvent.js');
const checkin = require('./checkin.js');
const hasTracingEnabled = require('./utils/hasTracingEnabled.js');
const isSentryRequestUrl = require('./utils/isSentryRequestUrl.js');
const constants = require('./constants.js');
const metadata = require('./integrations/metadata.js');
const requestdata = require('./integrations/requestdata.js');
const functiontostring = require('./integrations/functiontostring.js');
const inboundfilters = require('./integrations/inboundfilters.js');
const linkederrors = require('./integrations/linkederrors.js');



exports.addTracingExtensions = hubextensions.addTracingExtensions;
exports.startIdleTransaction = hubextensions.startIdleTransaction;
exports.IdleTransaction = idletransaction.IdleTransaction;
exports.TRACING_DEFAULTS = idletransaction.TRACING_DEFAULTS;
exports.Span = span.Span;
exports.spanStatusfromHttpCode = span.spanStatusfromHttpCode;
exports.Transaction = transaction.Transaction;
exports.extractTraceparentData = utils.extractTraceparentData;
exports.getActiveTransaction = utils.getActiveTransaction;
Object.defineProperty(exports, 'SpanStatus', {
  enumerable: true,
  get: () => spanstatus.SpanStatus
});
exports.continueTrace = trace.continueTrace;
exports.getActiveSpan = trace.getActiveSpan;
exports.startActiveSpan = trace.startActiveSpan;
exports.startInactiveSpan = trace.startInactiveSpan;
exports.startSpan = trace.startSpan;
exports.startSpanManual = trace.startSpanManual;
exports.trace = trace.trace;
exports.getDynamicSamplingContextFromClient = dynamicSamplingContext.getDynamicSamplingContextFromClient;
exports.setMeasurement = measurement.setMeasurement;
exports.createEventEnvelope = envelope.createEventEnvelope;
exports.addBreadcrumb = exports$1.addBreadcrumb;
exports.captureCheckIn = exports$1.captureCheckIn;
exports.captureEvent = exports$1.captureEvent;
exports.captureException = exports$1.captureException;
exports.captureMessage = exports$1.captureMessage;
exports.close = exports$1.close;
exports.configureScope = exports$1.configureScope;
exports.flush = exports$1.flush;
exports.getClient = exports$1.getClient;
exports.lastEventId = exports$1.lastEventId;
exports.setContext = exports$1.setContext;
exports.setExtra = exports$1.setExtra;
exports.setExtras = exports$1.setExtras;
exports.setTag = exports$1.setTag;
exports.setTags = exports$1.setTags;
exports.setUser = exports$1.setUser;
exports.startTransaction = exports$1.startTransaction;
exports.withMonitor = exports$1.withMonitor;
exports.withScope = exports$1.withScope;
exports.Hub = hub.Hub;
exports.ensureHubOnCarrier = hub.ensureHubOnCarrier;
exports.getCurrentHub = hub.getCurrentHub;
exports.getHubFromCarrier = hub.getHubFromCarrier;
exports.getMainCarrier = hub.getMainCarrier;
exports.makeMain = hub.makeMain;
exports.runWithAsyncContext = hub.runWithAsyncContext;
exports.setAsyncContextStrategy = hub.setAsyncContextStrategy;
exports.setHubOnCarrier = hub.setHubOnCarrier;
exports.closeSession = session.closeSession;
exports.makeSession = session.makeSession;
exports.updateSession = session.updateSession;
exports.SessionFlusher = sessionflusher.SessionFlusher;
exports.Scope = scope.Scope;
exports.addGlobalEventProcessor = eventProcessors.addGlobalEventProcessor;
exports.getEnvelopeEndpointWithUrlEncodedAuth = api.getEnvelopeEndpointWithUrlEncodedAuth;
exports.getReportDialogEndpoint = api.getReportDialogEndpoint;
exports.BaseClient = baseclient.BaseClient;
exports.addEventProcessor = baseclient.addEventProcessor;
exports.ServerRuntimeClient = serverRuntimeClient.ServerRuntimeClient;
exports.initAndBind = sdk.initAndBind;
exports.createTransport = base.createTransport;
exports.makeOfflineTransport = offline.makeOfflineTransport;
exports.makeMultiplexedTransport = multiplexed.makeMultiplexedTransport;
exports.SDK_VERSION = version.SDK_VERSION;
exports.addIntegration = integration.addIntegration;
exports.getIntegrationsToSetup = integration.getIntegrationsToSetup;
exports.Integrations = index;
exports.prepareEvent = prepareEvent.prepareEvent;
exports.createCheckInEnvelope = checkin.createCheckInEnvelope;
exports.hasTracingEnabled = hasTracingEnabled.hasTracingEnabled;
exports.isSentryRequestUrl = isSentryRequestUrl.isSentryRequestUrl;
exports.DEFAULT_ENVIRONMENT = constants.DEFAULT_ENVIRONMENT;
exports.ModuleMetadata = metadata.ModuleMetadata;
exports.RequestData = requestdata.RequestData;
exports.FunctionToString = functiontostring.FunctionToString;
exports.InboundFilters = inboundfilters.InboundFilters;
exports.LinkedErrors = linkederrors.LinkedErrors;


},{"./api.js":56,"./baseclient.js":57,"./checkin.js":58,"./constants.js":59,"./envelope.js":61,"./eventProcessors.js":62,"./exports.js":63,"./hub.js":64,"./integration.js":66,"./integrations/functiontostring.js":67,"./integrations/inboundfilters.js":68,"./integrations/index.js":69,"./integrations/linkederrors.js":70,"./integrations/metadata.js":71,"./integrations/requestdata.js":72,"./scope.js":74,"./sdk.js":75,"./server-runtime-client.js":76,"./session.js":77,"./sessionflusher.js":78,"./tracing/dynamicSamplingContext.js":79,"./tracing/hubextensions.js":81,"./tracing/idletransaction.js":82,"./tracing/measurement.js":83,"./tracing/span.js":85,"./tracing/spanstatus.js":86,"./tracing/trace.js":87,"./tracing/transaction.js":88,"./tracing/utils.js":89,"./transports/base.js":90,"./transports/multiplexed.js":91,"./transports/offline.js":92,"./utils/hasTracingEnabled.js":93,"./utils/isSentryRequestUrl.js":94,"./utils/prepareEvent.js":95,"./version.js":96}],66:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('./debug-build.js');
const eventProcessors = require('./eventProcessors.js');
const exports$1 = require('./exports.js');
const hub = require('./hub.js');

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

  return Object.keys(integrationsByName).map(k => integrationsByName[k]);
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
  const debugIndex = findIndex(finalIntegrations, integration => integration.name === 'Debug');
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
function setupIntegrations(client, integrations) {
  const integrationIndex = {};

  integrations.forEach(integration => {
    // guard against empty provided integrations
    if (integration) {
      setupIntegration(client, integration, integrationIndex);
    }
  });

  return integrationIndex;
}

/** Setup a single integration.  */
function setupIntegration(client, integration, integrationIndex) {
  integrationIndex[integration.name] = integration;

  // `setupOnce` is only called the first time
  if (installedIntegrations.indexOf(integration.name) === -1) {
    // eslint-disable-next-line deprecation/deprecation
    integration.setupOnce(eventProcessors.addGlobalEventProcessor, hub.getCurrentHub);
    installedIntegrations.push(integration.name);
  }

  // `setup` is run for each client
  if (integration.setup && typeof integration.setup === 'function') {
    integration.setup(client);
  }

  if (client.on && typeof integration.preprocessEvent === 'function') {
    const callback = integration.preprocessEvent.bind(integration) ;
    client.on('preprocessEvent', (event, hint) => callback(event, hint, client));
  }

  if (client.addEventProcessor && typeof integration.processEvent === 'function') {
    const callback = integration.processEvent.bind(integration) ;

    const processor = Object.assign((event, hint) => callback(event, hint, client), {
      id: integration.name,
    });

    client.addEventProcessor(processor);
  }

  debugBuild.DEBUG_BUILD && utils.logger.log(`Integration installed: ${integration.name}`);
}

/** Add an integration to the current hub's client. */
function addIntegration(integration) {
  const client = exports$1.getClient();

  if (!client || !client.addIntegration) {
    debugBuild.DEBUG_BUILD && utils.logger.warn(`Cannot add integration "${integration.name}" because no SDK Client is available.`);
    return;
  }

  client.addIntegration(integration);
}

// Polyfill for Array.findIndex(), which is not supported in ES5
function findIndex(arr, callback) {
  for (let i = 0; i < arr.length; i++) {
    if (callback(arr[i]) === true) {
      return i;
    }
  }

  return -1;
}

exports.addIntegration = addIntegration;
exports.getIntegrationsToSetup = getIntegrationsToSetup;
exports.installedIntegrations = installedIntegrations;
exports.setupIntegration = setupIntegration;
exports.setupIntegrations = setupIntegrations;


},{"./debug-build.js":60,"./eventProcessors.js":62,"./exports.js":63,"./hub.js":64,"@sentry/utils":117}],67:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

let originalFunctionToString;

/** Patch toString calls to return proper name for wrapped functions */
class FunctionToString  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'FunctionToString';}

  /**
   * @inheritDoc
   */

   constructor() {
    this.name = FunctionToString.id;
  }

  /**
   * @inheritDoc
   */
   setupOnce() {
    // eslint-disable-next-line @typescript-eslint/unbound-method
    originalFunctionToString = Function.prototype.toString;

    // intrinsics (like Function.prototype) might be immutable in some environments
    // e.g. Node with --frozen-intrinsics, XS (an embedded JavaScript engine) or SES (a JavaScript proposal)
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      Function.prototype.toString = function ( ...args) {
        const context = utils.getOriginalFunction(this) || this;
        return originalFunctionToString.apply(context, args);
      };
    } catch (e) {
      // ignore errors here, just don't patch this
    }
  }
} FunctionToString.__initStatic();

exports.FunctionToString = FunctionToString;


},{"@sentry/utils":117}],68:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');

// "Script error." is hard coded into browsers for errors that it can't read.
// this is the result of a script being pulled in from an external domain and CORS.
const DEFAULT_IGNORE_ERRORS = [/^Script error\.?$/, /^Javascript error: Script error\.? on line 0$/];

const DEFAULT_IGNORE_TRANSACTIONS = [
  /^.*\/healthcheck$/,
  /^.*\/healthy$/,
  /^.*\/live$/,
  /^.*\/ready$/,
  /^.*\/heartbeat$/,
  /^.*\/health$/,
  /^.*\/healthz$/,
];

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

   constructor(options = {}) {
    this.name = InboundFilters.id;
    this._options = options;
  }

  /**
   * @inheritDoc
   */
   setupOnce(_addGlobalEventProcessor, _getCurrentHub) {
    // noop
  }

  /** @inheritDoc */
   processEvent(event, _eventHint, client) {
    const clientOptions = client.getOptions();
    const options = _mergeOptions(this._options, clientOptions);
    return _shouldDropEvent(event, options) ? null : event;
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
      ...(internalOptions.disableErrorDefaults ? [] : DEFAULT_IGNORE_ERRORS),
    ],
    ignoreTransactions: [
      ...(internalOptions.ignoreTransactions || []),
      ...(clientOptions.ignoreTransactions || []),
      ...(internalOptions.disableTransactionDefaults ? [] : DEFAULT_IGNORE_TRANSACTIONS),
    ],
    ignoreInternal: internalOptions.ignoreInternal !== undefined ? internalOptions.ignoreInternal : true,
  };
}

/** JSDoc */
function _shouldDropEvent(event, options) {
  if (options.ignoreInternal && _isSentryError(event)) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.warn(`Event dropped due to being internal Sentry Error.\nEvent: ${utils.getEventDescription(event)}`);
    return true;
  }
  if (_isIgnoredError(event, options.ignoreErrors)) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.warn(
        `Event dropped due to being matched by \`ignoreErrors\` option.\nEvent: ${utils.getEventDescription(event)}`,
      );
    return true;
  }
  if (_isIgnoredTransaction(event, options.ignoreTransactions)) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.warn(
        `Event dropped due to being matched by \`ignoreTransactions\` option.\nEvent: ${utils.getEventDescription(event)}`,
      );
    return true;
  }
  if (_isDeniedUrl(event, options.denyUrls)) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.warn(
        `Event dropped due to being matched by \`denyUrls\` option.\nEvent: ${utils.getEventDescription(
          event,
        )}.\nUrl: ${_getEventFilterUrl(event)}`,
      );
    return true;
  }
  if (!_isAllowedUrl(event, options.allowUrls)) {
    debugBuild.DEBUG_BUILD &&
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
  // If event.type, this is not an error
  if (event.type || !ignoreErrors || !ignoreErrors.length) {
    return false;
  }

  return _getPossibleEventMessages(event).some(message => utils.stringMatchesSomePattern(message, ignoreErrors));
}

function _isIgnoredTransaction(event, ignoreTransactions) {
  if (event.type !== 'transaction' || !ignoreTransactions || !ignoreTransactions.length) {
    return false;
  }

  const name = event.transaction;
  return name ? utils.stringMatchesSomePattern(name, ignoreTransactions) : false;
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
  const possibleMessages = [];

  if (event.message) {
    possibleMessages.push(event.message);
  }

  let lastException;
  try {
    // @ts-expect-error Try catching to save bundle size
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    lastException = event.exception.values[event.exception.values.length - 1];
  } catch (e) {
    // try catching to save bundle size checking existence of variables
  }

  if (lastException) {
    if (lastException.value) {
      possibleMessages.push(lastException.value);
      if (lastException.type) {
        possibleMessages.push(`${lastException.type}: ${lastException.value}`);
      }
    }
  }

  if (debugBuild.DEBUG_BUILD && possibleMessages.length === 0) {
    utils.logger.error(`Could not extract message for event ${utils.getEventDescription(event)}`);
  }

  return possibleMessages;
}

function _isSentryError(event) {
  try {
    // @ts-expect-error can't be a sentry error if undefined
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
      // @ts-expect-error we only care about frames if the whole thing here is defined
      frames = event.exception.values[0].stacktrace.frames;
    } catch (e) {
      // ignore
    }
    return frames ? _getLastValidUrl(frames) : null;
  } catch (oO) {
    debugBuild.DEBUG_BUILD && utils.logger.error(`Cannot extract url for event ${utils.getEventDescription(event)}`);
    return null;
  }
}

exports.InboundFilters = InboundFilters;
exports._mergeOptions = _mergeOptions;
exports._shouldDropEvent = _shouldDropEvent;


},{"../debug-build.js":60,"@sentry/utils":117}],69:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const functiontostring = require('./functiontostring.js');
const inboundfilters = require('./inboundfilters.js');
const linkederrors = require('./linkederrors.js');



exports.FunctionToString = functiontostring.FunctionToString;
exports.InboundFilters = inboundfilters.InboundFilters;
exports.LinkedErrors = linkederrors.LinkedErrors;


},{"./functiontostring.js":67,"./inboundfilters.js":68,"./linkederrors.js":70}],70:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

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

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
   constructor(options = {}) {
    this._key = options.key || DEFAULT_KEY;
    this._limit = options.limit || DEFAULT_LIMIT;
    this.name = LinkedErrors.id;
  }

  /** @inheritdoc */
   setupOnce() {
    // noop
  }

  /**
   * @inheritDoc
   */
   preprocessEvent(event, hint, client) {
    const options = client.getOptions();

    utils.applyAggregateErrorsToEvent(
      utils.exceptionFromError,
      options.stackParser,
      options.maxValueLength,
      this._key,
      this._limit,
      event,
      hint,
    );
  }
} LinkedErrors.__initStatic();

exports.LinkedErrors = LinkedErrors;


},{"@sentry/utils":117}],71:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const metadata = require('../metadata.js');

/**
 * Adds module metadata to stack frames.
 *
 * Metadata can be injected by the Sentry bundler plugins using the `_experiments.moduleMetadata` config option.
 *
 * When this integration is added, the metadata passed to the bundler plugin is added to the stack frames of all events
 * under the `module_metadata` property. This can be used to help in tagging or routing of events from different teams
 * our sources
 */
class ModuleMetadata  {
  /*
   * @inheritDoc
   */
   static __initStatic() {this.id = 'ModuleMetadata';}

  /**
   * @inheritDoc
   */

   constructor() {
    this.name = ModuleMetadata.id;
  }

  /**
   * @inheritDoc
   */
   setupOnce(addGlobalEventProcessor, getCurrentHub) {
    const client = getCurrentHub().getClient();

    if (!client || typeof client.on !== 'function') {
      return;
    }

    // We need to strip metadata from stack frames before sending them to Sentry since these are client side only.
    client.on('beforeEnvelope', envelope => {
      utils.forEachEnvelopeItem(envelope, (item, type) => {
        if (type === 'event') {
          const event = Array.isArray(item) ? (item )[1] : undefined;

          if (event) {
            metadata.stripMetadataFromStackFrames(event);
            item[1] = event;
          }
        }
      });
    });

    const stackParser = client.getOptions().stackParser;

    addGlobalEventProcessor(event => {
      metadata.addMetadataToStackFrames(stackParser, event);
      return event;
    });
  }
} ModuleMetadata.__initStatic();

exports.ModuleMetadata = ModuleMetadata;


},{"../metadata.js":73,"@sentry/utils":117}],72:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

const DEFAULT_OPTIONS = {
  include: {
    cookies: true,
    data: true,
    headers: true,
    ip: false,
    query_string: true,
    url: true,
    user: {
      id: true,
      username: true,
      email: true,
    },
  },
  transactionNamingScheme: 'methodPath',
};

/** Add data about a request to an event. Primarily for use in Node-based SDKs, but included in `@sentry/integrations`
 * so it can be used in cross-platform SDKs like `@sentry/nextjs`. */
class RequestData  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'RequestData';}

  /**
   * @inheritDoc
   */

  /**
   * Function for adding request data to event. Defaults to `addRequestDataToEvent` from `@sentry/node` for now, but
   * left as a property so this integration can be moved to `@sentry/core` as a base class in case we decide to use
   * something similar in browser-based SDKs in the future.
   */

  /**
   * @inheritDoc
   */
   constructor(options = {}) {
    this.name = RequestData.id;
    this._addRequestData = utils.addRequestDataToEvent;
    this._options = {
      ...DEFAULT_OPTIONS,
      ...options,
      include: {
        // @ts-expect-error It's mad because `method` isn't a known `include` key. (It's only here and not set by default in
        // `addRequestDataToEvent` for legacy reasons. TODO (v8): Change that.)
        method: true,
        ...DEFAULT_OPTIONS.include,
        ...options.include,
        user:
          options.include && typeof options.include.user === 'boolean'
            ? options.include.user
            : {
                ...DEFAULT_OPTIONS.include.user,
                // Unclear why TS still thinks `options.include.user` could be a boolean at this point
                ...((options.include || {}).user ),
              },
      },
    };
  }

  /**
   * @inheritDoc
   */
   setupOnce(addGlobalEventProcessor, getCurrentHub) {
    // Note: In the long run, most of the logic here should probably move into the request data utility functions. For
    // the moment it lives here, though, until https://github.com/getsentry/sentry-javascript/issues/5718 is addressed.
    // (TL;DR: Those functions touch many parts of the repo in many different ways, and need to be clened up. Once
    // that's happened, it will be easier to add this logic in without worrying about unexpected side effects.)
    const { transactionNamingScheme } = this._options;

    addGlobalEventProcessor(event => {
      const hub = getCurrentHub();
      const self = hub.getIntegration(RequestData);

      const { sdkProcessingMetadata = {} } = event;
      const req = sdkProcessingMetadata.request;

      // If the globally installed instance of this integration isn't associated with the current hub, `self` will be
      // undefined
      if (!self || !req) {
        return event;
      }

      // The Express request handler takes a similar `include` option to that which can be passed to this integration.
      // If passed there, we store it in `sdkProcessingMetadata`. TODO(v8): Force express and GCP people to use this
      // integration, so that all of this passing and conversion isn't necessary
      const addRequestDataOptions =
        sdkProcessingMetadata.requestDataOptionsFromExpressHandler ||
        sdkProcessingMetadata.requestDataOptionsFromGCPWrapper ||
        convertReqDataIntegrationOptsToAddReqDataOpts(this._options);

      const processedEvent = this._addRequestData(event, req, addRequestDataOptions);

      // Transaction events already have the right `transaction` value
      if (event.type === 'transaction' || transactionNamingScheme === 'handler') {
        return processedEvent;
      }

      // In all other cases, use the request's associated transaction (if any) to overwrite the event's `transaction`
      // value with a high-quality one
      const reqWithTransaction = req ;
      const transaction = reqWithTransaction._sentryTransaction;
      if (transaction) {
        // TODO (v8): Remove the nextjs check and just base it on `transactionNamingScheme` for all SDKs. (We have to
        // keep it the way it is for the moment, because changing the names of transactions in Sentry has the potential
        // to break things like alert rules.)
        const shouldIncludeMethodInTransactionName =
          getSDKName(hub) === 'sentry.javascript.nextjs'
            ? transaction.name.startsWith('/api')
            : transactionNamingScheme !== 'path';

        const [transactionValue] = utils.extractPathForTransaction(req, {
          path: true,
          method: shouldIncludeMethodInTransactionName,
          customRoute: transaction.name,
        });

        processedEvent.transaction = transactionValue;
      }

      return processedEvent;
    });
  }
} RequestData.__initStatic();

/** Convert this integration's options to match what `addRequestDataToEvent` expects */
/** TODO: Can possibly be deleted once https://github.com/getsentry/sentry-javascript/issues/5718 is fixed */
function convertReqDataIntegrationOptsToAddReqDataOpts(
  integrationOptions,
) {
  const {
    transactionNamingScheme,
    include: { ip, user, ...requestOptions },
  } = integrationOptions;

  const requestIncludeKeys = [];
  for (const [key, value] of Object.entries(requestOptions)) {
    if (value) {
      requestIncludeKeys.push(key);
    }
  }

  let addReqDataUserOpt;
  if (user === undefined) {
    addReqDataUserOpt = true;
  } else if (typeof user === 'boolean') {
    addReqDataUserOpt = user;
  } else {
    const userIncludeKeys = [];
    for (const [key, value] of Object.entries(user)) {
      if (value) {
        userIncludeKeys.push(key);
      }
    }
    addReqDataUserOpt = userIncludeKeys;
  }

  return {
    include: {
      ip,
      user: addReqDataUserOpt,
      request: requestIncludeKeys.length !== 0 ? requestIncludeKeys : undefined,
      transaction: transactionNamingScheme,
    },
  };
}

function getSDKName(hub) {
  try {
    // For a long chain like this, it's fewer bytes to combine a try-catch with assuming everything is there than to
    // write out a long chain of `a && a.b && a.b.c && ...`
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    return hub.getClient().getOptions()._metadata.sdk.name;
  } catch (err) {
    // In theory we should never get here
    return undefined;
  }
}

exports.RequestData = RequestData;


},{"@sentry/utils":117}],73:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');

/** Keys are source filename/url, values are metadata objects. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const filenameMetadataMap = new Map();
/** Set of stack strings that have already been parsed. */
const parsedStacks = new Set();

function ensureMetadataStacksAreParsed(parser) {
  if (!utils.GLOBAL_OBJ._sentryModuleMetadata) {
    return;
  }

  for (const stack of Object.keys(utils.GLOBAL_OBJ._sentryModuleMetadata)) {
    const metadata = utils.GLOBAL_OBJ._sentryModuleMetadata[stack];

    if (parsedStacks.has(stack)) {
      continue;
    }

    // Ensure this stack doesn't get parsed again
    parsedStacks.add(stack);

    const frames = parser(stack);

    // Go through the frames starting from the top of the stack and find the first one with a filename
    for (const frame of frames.reverse()) {
      if (frame.filename) {
        // Save the metadata for this filename
        filenameMetadataMap.set(frame.filename, metadata);
        break;
      }
    }
  }
}

/**
 * Retrieve metadata for a specific JavaScript file URL.
 *
 * Metadata is injected by the Sentry bundler plugins using the `_experiments.moduleMetadata` config option.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getMetadataForUrl(parser, filename) {
  ensureMetadataStacksAreParsed(parser);
  return filenameMetadataMap.get(filename);
}

/**
 * Adds metadata to stack frames.
 *
 * Metadata is injected by the Sentry bundler plugins using the `_experiments.moduleMetadata` config option.
 */
function addMetadataToStackFrames(parser, event) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    event.exception.values.forEach(exception => {
      if (!exception.stacktrace) {
        return;
      }

      for (const frame of exception.stacktrace.frames || []) {
        if (!frame.filename) {
          continue;
        }

        const metadata = getMetadataForUrl(parser, frame.filename);

        if (metadata) {
          frame.module_metadata = metadata;
        }
      }
    });
  } catch (_) {
    // To save bundle size we're just try catching here instead of checking for the existence of all the different objects.
  }
}

/**
 * Strips metadata from stack frames.
 */
function stripMetadataFromStackFrames(event) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    event.exception.values.forEach(exception => {
      if (!exception.stacktrace) {
        return;
      }

      for (const frame of exception.stacktrace.frames || []) {
        delete frame.module_metadata;
      }
    });
  } catch (_) {
    // To save bundle size we're just try catching here instead of checking for the existence of all the different objects.
  }
}

exports.addMetadataToStackFrames = addMetadataToStackFrames;
exports.getMetadataForUrl = getMetadataForUrl;
exports.stripMetadataFromStackFrames = stripMetadataFromStackFrames;


},{"@sentry/utils":117}],74:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const eventProcessors = require('./eventProcessors.js');
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

  /** Propagation Context for distributed tracing */

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
    this._propagationContext = generatePropagationContext();
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
      newScope._propagationContext = { ...scope._propagationContext };
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
      if (captureContext._propagationContext) {
        this._propagationContext = captureContext._propagationContext;
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
      if (captureContext.propagationContext) {
        this._propagationContext = captureContext.propagationContext;
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
    this._propagationContext = generatePropagationContext();
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

    const breadcrumbs = this._breadcrumbs;
    breadcrumbs.push(mergedBreadcrumb);
    this._breadcrumbs = breadcrumbs.length > maxCrumbs ? breadcrumbs.slice(-maxCrumbs) : breadcrumbs;

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
   applyToEvent(
    event,
    hint = {},
    additionalEventProcessors,
  ) {
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
      const transaction = this._span.transaction;
      if (transaction) {
        event.sdkProcessingMetadata = {
          dynamicSamplingContext: transaction.getDynamicSamplingContext(),
          ...event.sdkProcessingMetadata,
        };
        const transactionName = transaction.name;
        if (transactionName) {
          event.tags = { transaction: transactionName, ...event.tags };
        }
      }
    }

    this._applyFingerprint(event);

    const scopeBreadcrumbs = this._getBreadcrumbs();
    const breadcrumbs = [...(event.breadcrumbs || []), ...scopeBreadcrumbs];
    event.breadcrumbs = breadcrumbs.length > 0 ? breadcrumbs : undefined;

    event.sdkProcessingMetadata = {
      ...event.sdkProcessingMetadata,
      ...this._sdkProcessingMetadata,
      propagationContext: this._propagationContext,
    };

    // TODO (v8): Update this order to be: Global > Client > Scope
    return eventProcessors.notifyEventProcessors(
      [
        ...(additionalEventProcessors || []),
        // eslint-disable-next-line deprecation/deprecation
        ...eventProcessors.getGlobalEventProcessors(),
        ...this._eventProcessors,
      ],
      event,
      hint,
    );
  }

  /**
   * Add data which will be accessible during event processing but won't get sent to Sentry
   */
   setSDKProcessingMetadata(newData) {
    this._sdkProcessingMetadata = { ...this._sdkProcessingMetadata, ...newData };

    return this;
  }

  /**
   * @inheritDoc
   */
   setPropagationContext(context) {
    this._propagationContext = context;
    return this;
  }

  /**
   * @inheritDoc
   */
   getPropagationContext() {
    return this._propagationContext;
  }

  /**
   * Get the breadcrumbs for this scope.
   */
   _getBreadcrumbs() {
    return this._breadcrumbs;
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

function generatePropagationContext() {
  return {
    traceId: utils.uuid4(),
    spanId: utils.uuid4().substring(16),
  };
}

exports.Scope = Scope;


},{"./eventProcessors.js":62,"./session.js":77,"@sentry/utils":117}],75:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('./debug-build.js');
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
    if (debugBuild.DEBUG_BUILD) {
      utils.logger.enable();
    } else {
      // use `console.warn` rather than `logger.warn` since by non-debug bundles have all `logger.x` statements stripped
      utils.consoleSandbox(() => {
        // eslint-disable-next-line no-console
        console.warn('[Sentry] Cannot initialize SDK with `debug` option using a non-debug bundle.');
      });
    }
  }
  const hub$1 = hub.getCurrentHub();
  const scope = hub$1.getScope();
  scope.update(options.initialScope);

  const client = new clientClass(options);
  hub$1.bindClient(client);
}

exports.initAndBind = initAndBind;


},{"./debug-build.js":60,"./hub.js":64,"@sentry/utils":117}],76:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const baseclient = require('./baseclient.js');
const checkin = require('./checkin.js');
const debugBuild = require('./debug-build.js');
const hub = require('./hub.js');
const sessionflusher = require('./sessionflusher.js');
const hubextensions = require('./tracing/hubextensions.js');
const dynamicSamplingContext = require('./tracing/dynamicSamplingContext.js');
require('./tracing/spanstatus.js');

/**
 * The Sentry Server Runtime Client SDK.
 */
class ServerRuntimeClient

 extends baseclient.BaseClient {

  /**
   * Creates a new Edge SDK instance.
   * @param options Configuration options for this SDK.
   */
   constructor(options) {
    // Server clients always support tracing
    hubextensions.addTracingExtensions();

    super(options);
  }

  /**
   * @inheritDoc
   */
   eventFromException(exception, hint) {
    return utils.resolvedSyncPromise(utils.eventFromUnknownInput(hub.getCurrentHub, this._options.stackParser, exception, hint));
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
    return utils.resolvedSyncPromise(
      utils.eventFromMessage(this._options.stackParser, message, level, hint, this._options.attachStacktrace),
    );
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
   captureException(exception, hint, scope) {
    // Check if the flag `autoSessionTracking` is enabled, and if `_sessionFlusher` exists because it is initialised only
    // when the `requestHandler` middleware is used, and hence the expectation is to have SessionAggregates payload
    // sent to the Server only when the `requestHandler` middleware is used
    if (this._options.autoSessionTracking && this._sessionFlusher && scope) {
      const requestSession = scope.getRequestSession();

      // Necessary checks to ensure this is code block is executed only within a request
      // Should override the status only if `requestSession.status` is `Ok`, which is its initial stage
      if (requestSession && requestSession.status === 'ok') {
        requestSession.status = 'errored';
      }
    }

    return super.captureException(exception, hint, scope);
  }

  /**
   * @inheritDoc
   */
   captureEvent(event, hint, scope) {
    // Check if the flag `autoSessionTracking` is enabled, and if `_sessionFlusher` exists because it is initialised only
    // when the `requestHandler` middleware is used, and hence the expectation is to have SessionAggregates payload
    // sent to the Server only when the `requestHandler` middleware is used
    if (this._options.autoSessionTracking && this._sessionFlusher && scope) {
      const eventType = event.type || 'exception';
      const isException =
        eventType === 'exception' && event.exception && event.exception.values && event.exception.values.length > 0;

      // If the event is of type Exception, then a request session should be captured
      if (isException) {
        const requestSession = scope.getRequestSession();

        // Ensure that this is happening within the bounds of a request, and make sure not to override
        // Session Status if Errored / Crashed
        if (requestSession && requestSession.status === 'ok') {
          requestSession.status = 'errored';
        }
      }
    }

    return super.captureEvent(event, hint, scope);
  }

  /**
   *
   * @inheritdoc
   */
   close(timeout) {
    if (this._sessionFlusher) {
      this._sessionFlusher.close();
    }
    return super.close(timeout);
  }

  /** Method that initialises an instance of SessionFlusher on Client */
   initSessionFlusher() {
    const { release, environment } = this._options;
    if (!release) {
      debugBuild.DEBUG_BUILD && utils.logger.warn('Cannot initialise an instance of SessionFlusher if no release is provided!');
    } else {
      this._sessionFlusher = new sessionflusher.SessionFlusher(this, {
        release,
        environment,
      });
    }
  }

  /**
   * Create a cron monitor check in and send it to Sentry.
   *
   * @param checkIn An object that describes a check in.
   * @param upsertMonitorConfig An optional object that describes a monitor config. Use this if you want
   * to create a monitor automatically when sending a check in.
   */
   captureCheckIn(checkIn, monitorConfig, scope) {
    const id = 'checkInId' in checkIn && checkIn.checkInId ? checkIn.checkInId : utils.uuid4();
    if (!this._isEnabled()) {
      debugBuild.DEBUG_BUILD && utils.logger.warn('SDK not enabled, will not capture checkin.');
      return id;
    }

    const options = this.getOptions();
    const { release, environment, tunnel } = options;

    const serializedCheckIn = {
      check_in_id: id,
      monitor_slug: checkIn.monitorSlug,
      status: checkIn.status,
      release,
      environment,
    };

    if ('duration' in checkIn) {
      serializedCheckIn.duration = checkIn.duration;
    }

    if (monitorConfig) {
      serializedCheckIn.monitor_config = {
        schedule: monitorConfig.schedule,
        checkin_margin: monitorConfig.checkinMargin,
        max_runtime: monitorConfig.maxRuntime,
        timezone: monitorConfig.timezone,
      };
    }

    const [dynamicSamplingContext, traceContext] = this._getTraceInfoFromScope(scope);
    if (traceContext) {
      serializedCheckIn.contexts = {
        trace: traceContext,
      };
    }

    const envelope = checkin.createCheckInEnvelope(
      serializedCheckIn,
      dynamicSamplingContext,
      this.getSdkMetadata(),
      tunnel,
      this.getDsn(),
    );

    debugBuild.DEBUG_BUILD && utils.logger.info('Sending checkin:', checkIn.monitorSlug, checkIn.status);
    void this._sendEnvelope(envelope);
    return id;
  }

  /**
   * Method responsible for capturing/ending a request session by calling `incrementSessionStatusCount` to increment
   * appropriate session aggregates bucket
   */
   _captureRequestSession() {
    if (!this._sessionFlusher) {
      debugBuild.DEBUG_BUILD && utils.logger.warn('Discarded request mode session because autoSessionTracking option was disabled');
    } else {
      this._sessionFlusher.incrementSessionStatusCount();
    }
  }

  /**
   * @inheritDoc
   */
   _prepareEvent(event, hint, scope) {
    if (this._options.platform) {
      event.platform = event.platform || this._options.platform;
    }

    if (this._options.runtime) {
      event.contexts = {
        ...event.contexts,
        runtime: (event.contexts || {}).runtime || this._options.runtime,
      };
    }

    if (this._options.serverName) {
      event.server_name = event.server_name || this._options.serverName;
    }

    return super._prepareEvent(event, hint, scope);
  }

  /** Extract trace information from scope */
   _getTraceInfoFromScope(
    scope,
  ) {
    if (!scope) {
      return [undefined, undefined];
    }

    const span = scope.getSpan();
    if (span) {
      const samplingContext = span.transaction ? span.transaction.getDynamicSamplingContext() : undefined;
      return [samplingContext, span.getTraceContext()];
    }

    const { traceId, spanId, parentSpanId, dsc } = scope.getPropagationContext();
    const traceContext = {
      trace_id: traceId,
      span_id: spanId,
      parent_span_id: parentSpanId,
    };
    if (dsc) {
      return [dsc, traceContext];
    }

    return [dynamicSamplingContext.getDynamicSamplingContextFromClient(traceId, this, scope), traceContext];
  }
}

exports.ServerRuntimeClient = ServerRuntimeClient;


},{"./baseclient.js":57,"./checkin.js":58,"./debug-build.js":60,"./hub.js":64,"./sessionflusher.js":78,"./tracing/dynamicSamplingContext.js":79,"./tracing/hubextensions.js":81,"./tracing/spanstatus.js":86,"@sentry/utils":117}],77:[function(require,module,exports){
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

  if (context.abnormal_mechanism) {
    session.abnormal_mechanism = context.abnormal_mechanism;
  }

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
    abnormal_mechanism: session.abnormal_mechanism,
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


},{"@sentry/utils":117}],78:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const hub = require('./hub.js');

/**
 * @inheritdoc
 */
class SessionFlusher  {

   constructor(client, attrs) {
    this._client = client;
    this.flushTimeout = 60;
    this._pendingAggregates = {};
    this._isEnabled = true;

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
    const requestSession = scope.getRequestSession();

    if (requestSession && requestSession.status) {
      this._incrementSessionStatusCount(requestSession.status, new Date());
      // This is not entirely necessarily but is added as a safe guard to indicate the bounds of a request and so in
      // case captureRequestSession is called more than once to prevent double count
      scope.setRequestSession(undefined);
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


},{"./hub.js":64,"@sentry/utils":117}],79:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const constants = require('../constants.js');

/**
 * Creates a dynamic sampling context from a client.
 *
 * Dispatchs the `createDsc` lifecycle hook as a side effect.
 */
function getDynamicSamplingContextFromClient(
  trace_id,
  client,
  scope,
) {
  const options = client.getOptions();

  const { publicKey: public_key } = client.getDsn() || {};
  const { segment: user_segment } = (scope && scope.getUser()) || {};

  const dsc = utils.dropUndefinedKeys({
    environment: options.environment || constants.DEFAULT_ENVIRONMENT,
    release: options.release,
    user_segment,
    public_key,
    trace_id,
  }) ;

  client.emit && client.emit('createDsc', dsc);

  return dsc;
}

exports.getDynamicSamplingContextFromClient = getDynamicSamplingContextFromClient;


},{"../constants.js":59,"@sentry/utils":117}],80:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const utils$1 = require('./utils.js');

let errorsInstrumented = false;

/**
 * Configures global error listeners
 */
function registerErrorInstrumentation() {
  if (errorsInstrumented) {
    return;
  }

  errorsInstrumented = true;
  utils.addGlobalErrorInstrumentationHandler(errorCallback);
  utils.addGlobalUnhandledRejectionInstrumentationHandler(errorCallback);
}

/**
 * If an error or unhandled promise occurs, we mark the active transaction as failed
 */
function errorCallback() {
  const activeTransaction = utils$1.getActiveTransaction();
  if (activeTransaction) {
    const status = 'internal_error';
    debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] Transaction: ${status} -> Global error occured`);
    activeTransaction.setStatus(status);
  }
}

// The function name will be lost when bundling but we need to be able to identify this listener later to maintain the
// node.js default exit behaviour
errorCallback.tag = 'sentry_tracingErrorCallback';

exports.registerErrorInstrumentation = registerErrorInstrumentation;


},{"../debug-build.js":60,"./utils.js":89,"@sentry/utils":117}],81:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const hub = require('../hub.js');
const errors = require('./errors.js');
const idletransaction = require('./idletransaction.js');
const sampling = require('./sampling.js');
const transaction = require('./transaction.js');

/** Returns all trace headers that are currently on the top scope. */
function traceHeaders() {
  const scope = this.getScope();
  const span = scope.getSpan();

  return span
    ? {
        'sentry-trace': span.toTraceparent(),
      }
    : {};
}

/**
 * Creates a new transaction and adds a sampling decision if it doesn't yet have one.
 *
 * The Hub.startTransaction method delegates to this method to do its work, passing the Hub instance in as `this`, as if
 * it had been called on the hub directly. Exists as a separate function so that it can be injected into the class as an
 * "extension method."
 *
 * @param this: The Hub starting the transaction
 * @param transactionContext: Data used to configure the transaction
 * @param CustomSamplingContext: Optional data to be provided to the `tracesSampler` function (if any)
 *
 * @returns The new transaction
 *
 * @see {@link Hub.startTransaction}
 */
function _startTransaction(

  transactionContext,
  customSamplingContext,
) {
  const client = this.getClient();
  const options = (client && client.getOptions()) || {};

  const configInstrumenter = options.instrumenter || 'sentry';
  const transactionInstrumenter = transactionContext.instrumenter || 'sentry';

  if (configInstrumenter !== transactionInstrumenter) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.error(
        `A transaction was started with instrumenter=\`${transactionInstrumenter}\`, but the SDK is configured with the \`${configInstrumenter}\` instrumenter.
The transaction will not be sampled. Please use the ${configInstrumenter} instrumentation to start transactions.`,
      );

    transactionContext.sampled = false;
  }

  let transaction$1 = new transaction.Transaction(transactionContext, this);
  transaction$1 = sampling.sampleTransaction(transaction$1, options, {
    parentSampled: transactionContext.parentSampled,
    transactionContext,
    ...customSamplingContext,
  });
  if (transaction$1.sampled) {
    transaction$1.initSpanRecorder(options._experiments && (options._experiments.maxSpans ));
  }
  if (client && client.emit) {
    client.emit('startTransaction', transaction$1);
  }
  return transaction$1;
}

/**
 * Create new idle transaction.
 */
function startIdleTransaction(
  hub,
  transactionContext,
  idleTimeout,
  finalTimeout,
  onScope,
  customSamplingContext,
  heartbeatInterval,
) {
  const client = hub.getClient();
  const options = (client && client.getOptions()) || {};

  let transaction = new idletransaction.IdleTransaction(transactionContext, hub, idleTimeout, finalTimeout, heartbeatInterval, onScope);
  transaction = sampling.sampleTransaction(transaction, options, {
    parentSampled: transactionContext.parentSampled,
    transactionContext,
    ...customSamplingContext,
  });
  if (transaction.sampled) {
    transaction.initSpanRecorder(options._experiments && (options._experiments.maxSpans ));
  }
  if (client && client.emit) {
    client.emit('startTransaction', transaction);
  }
  return transaction;
}

/**
 * Adds tracing extensions to the global hub.
 */
function addTracingExtensions() {
  const carrier = hub.getMainCarrier();
  if (!carrier.__SENTRY__) {
    return;
  }
  carrier.__SENTRY__.extensions = carrier.__SENTRY__.extensions || {};
  if (!carrier.__SENTRY__.extensions.startTransaction) {
    carrier.__SENTRY__.extensions.startTransaction = _startTransaction;
  }
  if (!carrier.__SENTRY__.extensions.traceHeaders) {
    carrier.__SENTRY__.extensions.traceHeaders = traceHeaders;
  }

  errors.registerErrorInstrumentation();
}

exports.addTracingExtensions = addTracingExtensions;
exports.startIdleTransaction = startIdleTransaction;


},{"../debug-build.js":60,"../hub.js":64,"./errors.js":80,"./idletransaction.js":82,"./sampling.js":84,"./transaction.js":88,"@sentry/utils":117}],82:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const span = require('./span.js');
const transaction = require('./transaction.js');

const TRACING_DEFAULTS = {
  idleTimeout: 1000,
  finalTimeout: 30000,
  heartbeatInterval: 5000,
};

const FINISH_REASON_TAG = 'finishReason';

const IDLE_TRANSACTION_FINISH_REASONS = [
  'heartbeatFailed',
  'idleTimeout',
  'documentHidden',
  'finalTimeout',
  'externalFinish',
  'cancelled',
];

/**
 * @inheritDoc
 */
class IdleTransactionSpanRecorder extends span.SpanRecorder {
   constructor(
      _pushActivity,
      _popActivity,
     transactionSpanId,
    maxlen,
  ) {
    super(maxlen);this._pushActivity = _pushActivity;this._popActivity = _popActivity;this.transactionSpanId = transactionSpanId;  }

  /**
   * @inheritDoc
   */
   add(span) {
    // We should make sure we do not push and pop activities for
    // the transaction that this span recorder belongs to.
    if (span.spanId !== this.transactionSpanId) {
      // We patch span.finish() to pop an activity after setting an endTimestamp.
      span.finish = (endTimestamp) => {
        span.endTimestamp = typeof endTimestamp === 'number' ? endTimestamp : utils.timestampInSeconds();
        this._popActivity(span.spanId);
      };

      // We should only push new activities if the span does not have an end timestamp.
      if (span.endTimestamp === undefined) {
        this._pushActivity(span.spanId);
      }
    }

    super.add(span);
  }
}

/**
 * An IdleTransaction is a transaction that automatically finishes. It does this by tracking child spans as activities.
 * You can have multiple IdleTransactions active, but if the `onScope` option is specified, the idle transaction will
 * put itself on the scope on creation.
 */
class IdleTransaction extends transaction.Transaction {
  // Activities store a list of active spans

  // Track state of activities in previous heartbeat

  // Amount of times heartbeat has counted. Will cause transaction to finish after 3 beats.

  // We should not use heartbeat if we finished a transaction

  // Idle timeout was canceled and we should finish the transaction with the last span end.

  /**
   * Timer that tracks Transaction idleTimeout
   */

   constructor(
    transactionContext,
      _idleHub,
    /**
     * The time to wait in ms until the idle transaction will be finished. This timer is started each time
     * there are no active spans on this transaction.
     */
      _idleTimeout = TRACING_DEFAULTS.idleTimeout,
    /**
     * The final value in ms that a transaction cannot exceed
     */
      _finalTimeout = TRACING_DEFAULTS.finalTimeout,
      _heartbeatInterval = TRACING_DEFAULTS.heartbeatInterval,
    // Whether or not the transaction should put itself on the scope when it starts and pop itself off when it ends
      _onScope = false,
  ) {
    super(transactionContext, _idleHub);this._idleHub = _idleHub;this._idleTimeout = _idleTimeout;this._finalTimeout = _finalTimeout;this._heartbeatInterval = _heartbeatInterval;this._onScope = _onScope;
    this.activities = {};
    this._heartbeatCounter = 0;
    this._finished = false;
    this._idleTimeoutCanceledPermanently = false;
    this._beforeFinishCallbacks = [];
    this._finishReason = IDLE_TRANSACTION_FINISH_REASONS[4];

    if (_onScope) {
      // We set the transaction here on the scope so error events pick up the trace
      // context and attach it to the error.
      debugBuild.DEBUG_BUILD && utils.logger.log(`Setting idle transaction on scope. Span ID: ${this.spanId}`);
      _idleHub.configureScope(scope => scope.setSpan(this));
    }

    this._restartIdleTimeout();
    setTimeout(() => {
      if (!this._finished) {
        this.setStatus('deadline_exceeded');
        this._finishReason = IDLE_TRANSACTION_FINISH_REASONS[3];
        this.finish();
      }
    }, this._finalTimeout);
  }

  /** {@inheritDoc} */
   finish(endTimestamp = utils.timestampInSeconds()) {
    this._finished = true;
    this.activities = {};

    if (this.op === 'ui.action.click') {
      this.setTag(FINISH_REASON_TAG, this._finishReason);
    }

    if (this.spanRecorder) {
      debugBuild.DEBUG_BUILD &&
        utils.logger.log('[Tracing] finishing IdleTransaction', new Date(endTimestamp * 1000).toISOString(), this.op);

      for (const callback of this._beforeFinishCallbacks) {
        callback(this, endTimestamp);
      }

      this.spanRecorder.spans = this.spanRecorder.spans.filter((span) => {
        // If we are dealing with the transaction itself, we just return it
        if (span.spanId === this.spanId) {
          return true;
        }

        // We cancel all pending spans with status "cancelled" to indicate the idle transaction was finished early
        if (!span.endTimestamp) {
          span.endTimestamp = endTimestamp;
          span.setStatus('cancelled');
          debugBuild.DEBUG_BUILD &&
            utils.logger.log('[Tracing] cancelling span since transaction ended early', JSON.stringify(span, undefined, 2));
        }

        const spanStartedBeforeTransactionFinish = span.startTimestamp < endTimestamp;

        // Add a delta with idle timeout so that we prevent false positives
        const timeoutWithMarginOfError = (this._finalTimeout + this._idleTimeout) / 1000;
        const spanEndedBeforeFinalTimeout = span.endTimestamp - this.startTimestamp < timeoutWithMarginOfError;

        if (debugBuild.DEBUG_BUILD) {
          const stringifiedSpan = JSON.stringify(span, undefined, 2);
          if (!spanStartedBeforeTransactionFinish) {
            utils.logger.log('[Tracing] discarding Span since it happened after Transaction was finished', stringifiedSpan);
          } else if (!spanEndedBeforeFinalTimeout) {
            utils.logger.log('[Tracing] discarding Span since it finished after Transaction final timeout', stringifiedSpan);
          }
        }

        return spanStartedBeforeTransactionFinish && spanEndedBeforeFinalTimeout;
      });

      debugBuild.DEBUG_BUILD && utils.logger.log('[Tracing] flushing IdleTransaction');
    } else {
      debugBuild.DEBUG_BUILD && utils.logger.log('[Tracing] No active IdleTransaction');
    }

    // if `this._onScope` is `true`, the transaction put itself on the scope when it started
    if (this._onScope) {
      const scope = this._idleHub.getScope();
      if (scope.getTransaction() === this) {
        scope.setSpan(undefined);
      }
    }

    return super.finish(endTimestamp);
  }

  /**
   * Register a callback function that gets excecuted before the transaction finishes.
   * Useful for cleanup or if you want to add any additional spans based on current context.
   *
   * This is exposed because users have no other way of running something before an idle transaction
   * finishes.
   */
   registerBeforeFinishCallback(callback) {
    this._beforeFinishCallbacks.push(callback);
  }

  /**
   * @inheritDoc
   */
   initSpanRecorder(maxlen) {
    if (!this.spanRecorder) {
      const pushActivity = (id) => {
        if (this._finished) {
          return;
        }
        this._pushActivity(id);
      };
      const popActivity = (id) => {
        if (this._finished) {
          return;
        }
        this._popActivity(id);
      };

      this.spanRecorder = new IdleTransactionSpanRecorder(pushActivity, popActivity, this.spanId, maxlen);

      // Start heartbeat so that transactions do not run forever.
      debugBuild.DEBUG_BUILD && utils.logger.log('Starting heartbeat');
      this._pingHeartbeat();
    }
    this.spanRecorder.add(this);
  }

  /**
   * Cancels the existing idle timeout, if there is one.
   * @param restartOnChildSpanChange Default is `true`.
   *                                 If set to false the transaction will end
   *                                 with the last child span.
   */
   cancelIdleTimeout(
    endTimestamp,
    {
      restartOnChildSpanChange,
    }

 = {
      restartOnChildSpanChange: true,
    },
  ) {
    this._idleTimeoutCanceledPermanently = restartOnChildSpanChange === false;
    if (this._idleTimeoutID) {
      clearTimeout(this._idleTimeoutID);
      this._idleTimeoutID = undefined;

      if (Object.keys(this.activities).length === 0 && this._idleTimeoutCanceledPermanently) {
        this._finishReason = IDLE_TRANSACTION_FINISH_REASONS[5];
        this.finish(endTimestamp);
      }
    }
  }

  /**
   * Temporary method used to externally set the transaction's `finishReason`
   *
   * ** WARNING**
   * This is for the purpose of experimentation only and will be removed in the near future, do not use!
   *
   * @internal
   *
   */
   setFinishReason(reason) {
    this._finishReason = reason;
  }

  /**
   * Restarts idle timeout, if there is no running idle timeout it will start one.
   */
   _restartIdleTimeout(endTimestamp) {
    this.cancelIdleTimeout();
    this._idleTimeoutID = setTimeout(() => {
      if (!this._finished && Object.keys(this.activities).length === 0) {
        this._finishReason = IDLE_TRANSACTION_FINISH_REASONS[1];
        this.finish(endTimestamp);
      }
    }, this._idleTimeout);
  }

  /**
   * Start tracking a specific activity.
   * @param spanId The span id that represents the activity
   */
   _pushActivity(spanId) {
    this.cancelIdleTimeout(undefined, { restartOnChildSpanChange: !this._idleTimeoutCanceledPermanently });
    debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] pushActivity: ${spanId}`);
    this.activities[spanId] = true;
    debugBuild.DEBUG_BUILD && utils.logger.log('[Tracing] new activities count', Object.keys(this.activities).length);
  }

  /**
   * Remove an activity from usage
   * @param spanId The span id that represents the activity
   */
   _popActivity(spanId) {
    if (this.activities[spanId]) {
      debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] popActivity ${spanId}`);
      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
      delete this.activities[spanId];
      debugBuild.DEBUG_BUILD && utils.logger.log('[Tracing] new activities count', Object.keys(this.activities).length);
    }

    if (Object.keys(this.activities).length === 0) {
      const endTimestamp = utils.timestampInSeconds();
      if (this._idleTimeoutCanceledPermanently) {
        this._finishReason = IDLE_TRANSACTION_FINISH_REASONS[5];
        this.finish(endTimestamp);
      } else {
        // We need to add the timeout here to have the real endtimestamp of the transaction
        // Remember timestampInSeconds is in seconds, timeout is in ms
        this._restartIdleTimeout(endTimestamp + this._idleTimeout / 1000);
      }
    }
  }

  /**
   * Checks when entries of this.activities are not changing for 3 beats.
   * If this occurs we finish the transaction.
   */
   _beat() {
    // We should not be running heartbeat if the idle transaction is finished.
    if (this._finished) {
      return;
    }

    const heartbeatString = Object.keys(this.activities).join('');

    if (heartbeatString === this._prevHeartbeatString) {
      this._heartbeatCounter++;
    } else {
      this._heartbeatCounter = 1;
    }

    this._prevHeartbeatString = heartbeatString;

    if (this._heartbeatCounter >= 3) {
      debugBuild.DEBUG_BUILD && utils.logger.log('[Tracing] Transaction finished because of no change for 3 heart beats');
      this.setStatus('deadline_exceeded');
      this._finishReason = IDLE_TRANSACTION_FINISH_REASONS[0];
      this.finish();
    } else {
      this._pingHeartbeat();
    }
  }

  /**
   * Pings the heartbeat
   */
   _pingHeartbeat() {
    debugBuild.DEBUG_BUILD && utils.logger.log(`pinging Heartbeat -> current counter: ${this._heartbeatCounter}`);
    setTimeout(() => {
      this._beat();
    }, this._heartbeatInterval);
  }
}

exports.IdleTransaction = IdleTransaction;
exports.IdleTransactionSpanRecorder = IdleTransactionSpanRecorder;
exports.TRACING_DEFAULTS = TRACING_DEFAULTS;


},{"../debug-build.js":60,"./span.js":85,"./transaction.js":88,"@sentry/utils":117}],83:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('./utils.js');

/**
 * Adds a measurement to the current active transaction.
 */
function setMeasurement(name, value, unit) {
  const transaction = utils.getActiveTransaction();
  if (transaction) {
    transaction.setMeasurement(name, value, unit);
  }
}

exports.setMeasurement = setMeasurement;


},{"./utils.js":89}],84:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const hasTracingEnabled = require('../utils/hasTracingEnabled.js');

/**
 * Makes a sampling decision for the given transaction and stores it on the transaction.
 *
 * Called every time a transaction is created. Only transactions which emerge with a `sampled` value of `true` will be
 * sent to Sentry.
 *
 * This method muttes the given `transaction` and will set the `sampled` value on it.
 * It returns the same transaction, for convenience.
 */
function sampleTransaction(
  transaction,
  options,
  samplingContext,
) {
  // nothing to do if tracing is not enabled
  if (!hasTracingEnabled.hasTracingEnabled(options)) {
    transaction.sampled = false;
    return transaction;
  }

  // if the user has forced a sampling decision by passing a `sampled` value in their transaction context, go with that
  if (transaction.sampled !== undefined) {
    transaction.setMetadata({
      sampleRate: Number(transaction.sampled),
    });
    return transaction;
  }

  // we would have bailed already if neither `tracesSampler` nor `tracesSampleRate` nor `enableTracing` were defined, so one of these should
  // work; prefer the hook if so
  let sampleRate;
  if (typeof options.tracesSampler === 'function') {
    sampleRate = options.tracesSampler(samplingContext);
    transaction.setMetadata({
      sampleRate: Number(sampleRate),
    });
  } else if (samplingContext.parentSampled !== undefined) {
    sampleRate = samplingContext.parentSampled;
  } else if (typeof options.tracesSampleRate !== 'undefined') {
    sampleRate = options.tracesSampleRate;
    transaction.setMetadata({
      sampleRate: Number(sampleRate),
    });
  } else {
    // When `enableTracing === true`, we use a sample rate of 100%
    sampleRate = 1;
    transaction.setMetadata({
      sampleRate,
    });
  }

  // Since this is coming from the user (or from a function provided by the user), who knows what we might get. (The
  // only valid values are booleans or numbers between 0 and 1.)
  if (!isValidSampleRate(sampleRate)) {
    debugBuild.DEBUG_BUILD && utils.logger.warn('[Tracing] Discarding transaction because of invalid sample rate.');
    transaction.sampled = false;
    return transaction;
  }

  // if the function returned 0 (or false), or if `tracesSampleRate` is 0, it's a sign the transaction should be dropped
  if (!sampleRate) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.log(
        `[Tracing] Discarding transaction because ${
          typeof options.tracesSampler === 'function'
            ? 'tracesSampler returned 0 or false'
            : 'a negative sampling decision was inherited or tracesSampleRate is set to 0'
        }`,
      );
    transaction.sampled = false;
    return transaction;
  }

  // Now we roll the dice. Math.random is inclusive of 0, but not of 1, so strict < is safe here. In case sampleRate is
  // a boolean, the < comparison will cause it to be automatically cast to 1 if it's true and 0 if it's false.
  transaction.sampled = Math.random() < (sampleRate );

  // if we're not going to keep it, we're done
  if (!transaction.sampled) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.log(
        `[Tracing] Discarding transaction because it's not included in the random sample (sampling rate = ${Number(
          sampleRate,
        )})`,
      );
    return transaction;
  }

  debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] starting ${transaction.op} transaction - ${transaction.name}`);
  return transaction;
}

/**
 * Checks the given sample rate to make sure it is valid type and value (a boolean, or a number between 0 and 1).
 */
function isValidSampleRate(rate) {
  // we need to check NaN explicitly because it's of type 'number' and therefore wouldn't get caught by this typecheck
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (utils.isNaN(rate) || !(typeof rate === 'number' || typeof rate === 'boolean')) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.warn(
        `[Tracing] Given sample rate is invalid. Sample rate must be a boolean or a number between 0 and 1. Got ${JSON.stringify(
          rate,
        )} of type ${JSON.stringify(typeof rate)}.`,
      );
    return false;
  }

  // in case sampleRate is a boolean, it will get automatically cast to 1 if it's true and 0 if it's false
  if (rate < 0 || rate > 1) {
    debugBuild.DEBUG_BUILD &&
      utils.logger.warn(`[Tracing] Given sample rate is invalid. Sample rate must be between 0 and 1. Got ${rate}.`);
    return false;
  }
  return true;
}

exports.sampleTransaction = sampleTransaction;


},{"../debug-build.js":60,"../utils/hasTracingEnabled.js":93,"@sentry/utils":117}],85:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');

/**
 * Keeps track of finished spans for a given transaction
 * @internal
 * @hideconstructor
 * @hidden
 */
class SpanRecorder {

   constructor(maxlen = 1000) {
    this._maxlen = maxlen;
    this.spans = [];
  }

  /**
   * This is just so that we don't run out of memory while recording a lot
   * of spans. At some point we just stop and flush out the start of the
   * trace tree (i.e.the first n spans with the smallest
   * start_timestamp).
   */
   add(span) {
    if (this.spans.length > this._maxlen) {
      span.spanRecorder = undefined;
    } else {
      this.spans.push(span);
    }
  }
}

/**
 * Span contains all data about a span
 */
class Span  {
  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

  /**
   * Internal keeper of the status
   */

  /**
   * @inheritDoc
   */

  /**
   * Timestamp in seconds when the span was created.
   */

  /**
   * Timestamp in seconds when the span ended.
   */

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any

  /**
   * List of spans that were finalized
   */

  /**
   * @inheritDoc
   */

  /**
   * The instrumenter that created this span.
   */

  /**
   * The origin of the span, giving context about what created the span.
   */

  /**
   * You should never call the constructor manually, always use `Sentry.startTransaction()`
   * or call `startChild()` on an existing span.
   * @internal
   * @hideconstructor
   * @hidden
   */
   constructor(spanContext = {}) {
    this.traceId = spanContext.traceId || utils.uuid4();
    this.spanId = spanContext.spanId || utils.uuid4().substring(16);
    this.startTimestamp = spanContext.startTimestamp || utils.timestampInSeconds();
    this.tags = spanContext.tags || {};
    this.data = spanContext.data || {};
    this.instrumenter = spanContext.instrumenter || 'sentry';
    this.origin = spanContext.origin || 'manual';

    if (spanContext.parentSpanId) {
      this.parentSpanId = spanContext.parentSpanId;
    }
    // We want to include booleans as well here
    if ('sampled' in spanContext) {
      this.sampled = spanContext.sampled;
    }
    if (spanContext.op) {
      this.op = spanContext.op;
    }
    if (spanContext.description) {
      this.description = spanContext.description;
    }
    if (spanContext.name) {
      this.description = spanContext.name;
    }
    if (spanContext.status) {
      this.status = spanContext.status;
    }
    if (spanContext.endTimestamp) {
      this.endTimestamp = spanContext.endTimestamp;
    }
  }

  /** An alias for `description` of the Span. */
   get name() {
    return this.description || '';
  }
  /** Update the name of the span. */
   set name(name) {
    this.setName(name);
  }

  /**
   * @inheritDoc
   */
   startChild(
    spanContext,
  ) {
    const childSpan = new Span({
      ...spanContext,
      parentSpanId: this.spanId,
      sampled: this.sampled,
      traceId: this.traceId,
    });

    childSpan.spanRecorder = this.spanRecorder;
    if (childSpan.spanRecorder) {
      childSpan.spanRecorder.add(childSpan);
    }

    childSpan.transaction = this.transaction;

    if (debugBuild.DEBUG_BUILD && childSpan.transaction) {
      const opStr = (spanContext && spanContext.op) || '< unknown op >';
      const nameStr = childSpan.transaction.name || '< unknown name >';
      const idStr = childSpan.transaction.spanId;

      const logMessage = `[Tracing] Starting '${opStr}' span on transaction '${nameStr}' (${idStr}).`;
      childSpan.transaction.metadata.spanMetadata[childSpan.spanId] = { logMessage };
      utils.logger.log(logMessage);
    }

    return childSpan;
  }

  /**
   * @inheritDoc
   */
   setTag(key, value) {
    this.tags = { ...this.tags, [key]: value };
    return this;
  }

  /**
   * @inheritDoc
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/explicit-module-boundary-types
   setData(key, value) {
    this.data = { ...this.data, [key]: value };
    return this;
  }

  /**
   * @inheritDoc
   */
   setStatus(value) {
    this.status = value;
    return this;
  }

  /**
   * @inheritDoc
   */
   setHttpStatus(httpStatus) {
    this.setTag('http.status_code', String(httpStatus));
    this.setData('http.response.status_code', httpStatus);
    const spanStatus = spanStatusfromHttpCode(httpStatus);
    if (spanStatus !== 'unknown_error') {
      this.setStatus(spanStatus);
    }
    return this;
  }

  /**
   * @inheritDoc
   */
   setName(name) {
    this.description = name;
  }

  /**
   * @inheritDoc
   */
   isSuccess() {
    return this.status === 'ok';
  }

  /**
   * @inheritDoc
   */
   finish(endTimestamp) {
    if (
      debugBuild.DEBUG_BUILD &&
      // Don't call this for transactions
      this.transaction &&
      this.transaction.spanId !== this.spanId
    ) {
      const { logMessage } = this.transaction.metadata.spanMetadata[this.spanId];
      if (logMessage) {
        utils.logger.log((logMessage ).replace('Starting', 'Finishing'));
      }
    }

    this.endTimestamp = typeof endTimestamp === 'number' ? endTimestamp : utils.timestampInSeconds();
  }

  /**
   * @inheritDoc
   */
   toTraceparent() {
    return utils.generateSentryTraceHeader(this.traceId, this.spanId, this.sampled);
  }

  /**
   * @inheritDoc
   */
   toContext() {
    return utils.dropUndefinedKeys({
      data: this.data,
      description: this.description,
      endTimestamp: this.endTimestamp,
      op: this.op,
      parentSpanId: this.parentSpanId,
      sampled: this.sampled,
      spanId: this.spanId,
      startTimestamp: this.startTimestamp,
      status: this.status,
      tags: this.tags,
      traceId: this.traceId,
    });
  }

  /**
   * @inheritDoc
   */
   updateWithContext(spanContext) {
    this.data = spanContext.data || {};
    this.description = spanContext.description;
    this.endTimestamp = spanContext.endTimestamp;
    this.op = spanContext.op;
    this.parentSpanId = spanContext.parentSpanId;
    this.sampled = spanContext.sampled;
    this.spanId = spanContext.spanId || this.spanId;
    this.startTimestamp = spanContext.startTimestamp || this.startTimestamp;
    this.status = spanContext.status;
    this.tags = spanContext.tags || {};
    this.traceId = spanContext.traceId || this.traceId;

    return this;
  }

  /**
   * @inheritDoc
   */
   getTraceContext() {
    return utils.dropUndefinedKeys({
      data: Object.keys(this.data).length > 0 ? this.data : undefined,
      description: this.description,
      op: this.op,
      parent_span_id: this.parentSpanId,
      span_id: this.spanId,
      status: this.status,
      tags: Object.keys(this.tags).length > 0 ? this.tags : undefined,
      trace_id: this.traceId,
      origin: this.origin,
    });
  }

  /**
   * @inheritDoc
   */
   toJSON()

 {
    return utils.dropUndefinedKeys({
      data: Object.keys(this.data).length > 0 ? this.data : undefined,
      description: this.description,
      op: this.op,
      parent_span_id: this.parentSpanId,
      span_id: this.spanId,
      start_timestamp: this.startTimestamp,
      status: this.status,
      tags: Object.keys(this.tags).length > 0 ? this.tags : undefined,
      timestamp: this.endTimestamp,
      trace_id: this.traceId,
      origin: this.origin,
    });
  }
}

/**
 * Converts a HTTP status code into a {@link SpanStatusType}.
 *
 * @param httpStatus The HTTP response status code.
 * @returns The span status or unknown_error.
 */
function spanStatusfromHttpCode(httpStatus) {
  if (httpStatus < 400 && httpStatus >= 100) {
    return 'ok';
  }

  if (httpStatus >= 400 && httpStatus < 500) {
    switch (httpStatus) {
      case 401:
        return 'unauthenticated';
      case 403:
        return 'permission_denied';
      case 404:
        return 'not_found';
      case 409:
        return 'already_exists';
      case 413:
        return 'failed_precondition';
      case 429:
        return 'resource_exhausted';
      default:
        return 'invalid_argument';
    }
  }

  if (httpStatus >= 500 && httpStatus < 600) {
    switch (httpStatus) {
      case 501:
        return 'unimplemented';
      case 503:
        return 'unavailable';
      case 504:
        return 'deadline_exceeded';
      default:
        return 'internal_error';
    }
  }

  return 'unknown_error';
}

exports.Span = Span;
exports.SpanRecorder = SpanRecorder;
exports.spanStatusfromHttpCode = spanStatusfromHttpCode;


},{"../debug-build.js":60,"@sentry/utils":117}],86:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/** The status of an Span.
 *
 * @deprecated Use string literals - if you require type casting, cast to SpanStatusType type
 */
exports.SpanStatus = void 0; (function (SpanStatus) {
  /** The operation completed successfully. */
  const Ok = 'ok'; SpanStatus["Ok"] = Ok;
  /** Deadline expired before operation could complete. */
  const DeadlineExceeded = 'deadline_exceeded'; SpanStatus["DeadlineExceeded"] = DeadlineExceeded;
  /** 401 Unauthorized (actually does mean unauthenticated according to RFC 7235) */
  const Unauthenticated = 'unauthenticated'; SpanStatus["Unauthenticated"] = Unauthenticated;
  /** 403 Forbidden */
  const PermissionDenied = 'permission_denied'; SpanStatus["PermissionDenied"] = PermissionDenied;
  /** 404 Not Found. Some requested entity (file or directory) was not found. */
  const NotFound = 'not_found'; SpanStatus["NotFound"] = NotFound;
  /** 429 Too Many Requests */
  const ResourceExhausted = 'resource_exhausted'; SpanStatus["ResourceExhausted"] = ResourceExhausted;
  /** Client specified an invalid argument. 4xx. */
  const InvalidArgument = 'invalid_argument'; SpanStatus["InvalidArgument"] = InvalidArgument;
  /** 501 Not Implemented */
  const Unimplemented = 'unimplemented'; SpanStatus["Unimplemented"] = Unimplemented;
  /** 503 Service Unavailable */
  const Unavailable = 'unavailable'; SpanStatus["Unavailable"] = Unavailable;
  /** Other/generic 5xx. */
  const InternalError = 'internal_error'; SpanStatus["InternalError"] = InternalError;
  /** Unknown. Any non-standard HTTP status code. */
  const UnknownError = 'unknown_error'; SpanStatus["UnknownError"] = UnknownError;
  /** The operation was cancelled (typically by the user). */
  const Cancelled = 'cancelled'; SpanStatus["Cancelled"] = Cancelled;
  /** Already exists (409) */
  const AlreadyExists = 'already_exists'; SpanStatus["AlreadyExists"] = AlreadyExists;
  /** Operation was rejected because the system is not in a state required for the operation's */
  const FailedPrecondition = 'failed_precondition'; SpanStatus["FailedPrecondition"] = FailedPrecondition;
  /** The operation was aborted, typically due to a concurrency issue. */
  const Aborted = 'aborted'; SpanStatus["Aborted"] = Aborted;
  /** Operation was attempted past the valid range. */
  const OutOfRange = 'out_of_range'; SpanStatus["OutOfRange"] = OutOfRange;
  /** Unrecoverable data loss or corruption */
  const DataLoss = 'data_loss'; SpanStatus["DataLoss"] = DataLoss;
})(exports.SpanStatus || (exports.SpanStatus = {}));


},{}],87:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const hub = require('../hub.js');
const hasTracingEnabled = require('../utils/hasTracingEnabled.js');

/**
 * Wraps a function with a transaction/span and finishes the span after the function is done.
 *
 * Note that if you have not enabled tracing extensions via `addTracingExtensions`
 * or you didn't set `tracesSampleRate`, this function will not generate spans
 * and the `span` returned from the callback will be undefined.
 *
 * This function is meant to be used internally and may break at any time. Use at your own risk.
 *
 * @internal
 * @private
 */
function trace(
  context,
  callback,
  // eslint-disable-next-line @typescript-eslint/no-empty-function
  onError = () => {},
) {
  const ctx = normalizeContext(context);

  const hub$1 = hub.getCurrentHub();
  const scope = hub$1.getScope();
  const parentSpan = scope.getSpan();

  const activeSpan = createChildSpanOrTransaction(hub$1, parentSpan, ctx);

  scope.setSpan(activeSpan);

  function finishAndSetSpan() {
    activeSpan && activeSpan.finish();
    hub$1.getScope().setSpan(parentSpan);
  }

  let maybePromiseResult;
  try {
    maybePromiseResult = callback(activeSpan);
  } catch (e) {
    activeSpan && activeSpan.setStatus('internal_error');
    onError(e);
    finishAndSetSpan();
    throw e;
  }

  if (utils.isThenable(maybePromiseResult)) {
    Promise.resolve(maybePromiseResult).then(
      () => {
        finishAndSetSpan();
      },
      e => {
        activeSpan && activeSpan.setStatus('internal_error');
        onError(e);
        finishAndSetSpan();
      },
    );
  } else {
    finishAndSetSpan();
  }

  return maybePromiseResult;
}

/**
 * Wraps a function with a transaction/span and finishes the span after the function is done.
 * The created span is the active span and will be used as parent by other spans created inside the function
 * and can be accessed via `Sentry.getSpan()`, as long as the function is executed while the scope is active.
 *
 * If you want to create a span that is not set as active, use {@link startInactiveSpan}.
 *
 * Note that if you have not enabled tracing extensions via `addTracingExtensions`
 * or you didn't set `tracesSampleRate`, this function will not generate spans
 * and the `span` returned from the callback will be undefined.
 */
function startSpan(context, callback) {
  const ctx = normalizeContext(context);

  const hub$1 = hub.getCurrentHub();
  const scope = hub$1.getScope();
  const parentSpan = scope.getSpan();

  const activeSpan = createChildSpanOrTransaction(hub$1, parentSpan, ctx);
  scope.setSpan(activeSpan);

  function finishAndSetSpan() {
    activeSpan && activeSpan.finish();
    hub$1.getScope().setSpan(parentSpan);
  }

  let maybePromiseResult;
  try {
    maybePromiseResult = callback(activeSpan);
  } catch (e) {
    activeSpan && activeSpan.setStatus('internal_error');
    finishAndSetSpan();
    throw e;
  }

  if (utils.isThenable(maybePromiseResult)) {
    Promise.resolve(maybePromiseResult).then(
      () => {
        finishAndSetSpan();
      },
      () => {
        activeSpan && activeSpan.setStatus('internal_error');
        finishAndSetSpan();
      },
    );
  } else {
    finishAndSetSpan();
  }

  return maybePromiseResult;
}

/**
 * @deprecated Use {@link startSpan} instead.
 */
const startActiveSpan = startSpan;

/**
 * Similar to `Sentry.startSpan`. Wraps a function with a transaction/span, but does not finish the span
 * after the function is done automatically.
 *
 * The created span is the active span and will be used as parent by other spans created inside the function
 * and can be accessed via `Sentry.getActiveSpan()`, as long as the function is executed while the scope is active.
 *
 * Note that if you have not enabled tracing extensions via `addTracingExtensions`
 * or you didn't set `tracesSampleRate`, this function will not generate spans
 * and the `span` returned from the callback will be undefined.
 */
function startSpanManual(
  context,
  callback,
) {
  const ctx = normalizeContext(context);

  const hub$1 = hub.getCurrentHub();
  const scope = hub$1.getScope();
  const parentSpan = scope.getSpan();

  const activeSpan = createChildSpanOrTransaction(hub$1, parentSpan, ctx);
  scope.setSpan(activeSpan);

  function finishAndSetSpan() {
    activeSpan && activeSpan.finish();
    hub$1.getScope().setSpan(parentSpan);
  }

  let maybePromiseResult;
  try {
    maybePromiseResult = callback(activeSpan, finishAndSetSpan);
  } catch (e) {
    activeSpan && activeSpan.setStatus('internal_error');
    throw e;
  }

  if (utils.isThenable(maybePromiseResult)) {
    Promise.resolve(maybePromiseResult).then(undefined, () => {
      activeSpan && activeSpan.setStatus('internal_error');
    });
  }

  return maybePromiseResult;
}

/**
 * Creates a span. This span is not set as active, so will not get automatic instrumentation spans
 * as children or be able to be accessed via `Sentry.getSpan()`.
 *
 * If you want to create a span that is set as active, use {@link startSpan}.
 *
 * Note that if you have not enabled tracing extensions via `addTracingExtensions`
 * or you didn't set `tracesSampleRate` or `tracesSampler`, this function will not generate spans
 * and the `span` returned from the callback will be undefined.
 */
function startInactiveSpan(context) {
  if (!hasTracingEnabled.hasTracingEnabled()) {
    return undefined;
  }

  const ctx = { ...context };
  // If a name is set and a description is not, set the description to the name.
  if (ctx.name !== undefined && ctx.description === undefined) {
    ctx.description = ctx.name;
  }

  const hub$1 = hub.getCurrentHub();
  const parentSpan = getActiveSpan();
  return parentSpan ? parentSpan.startChild(ctx) : hub$1.startTransaction(ctx);
}

/**
 * Returns the currently active span.
 */
function getActiveSpan() {
  return hub.getCurrentHub().getScope().getSpan();
}

/**
 * Continue a trace from `sentry-trace` and `baggage` values.
 * These values can be obtained from incoming request headers,
 * or in the browser from `<meta name="sentry-trace">` and `<meta name="baggage">` HTML tags.
 *
 * The callback receives a transactionContext that may be used for `startTransaction` or `startSpan`.
 */
function continueTrace(
  {
    sentryTrace,
    baggage,
  }

,
  callback,
) {
  const hub$1 = hub.getCurrentHub();
  const currentScope = hub$1.getScope();

  const { traceparentData, dynamicSamplingContext, propagationContext } = utils.tracingContextFromHeaders(
    sentryTrace,
    baggage,
  );

  currentScope.setPropagationContext(propagationContext);

  if (debugBuild.DEBUG_BUILD && traceparentData) {
    utils.logger.log(`[Tracing] Continuing trace ${traceparentData.traceId}.`);
  }

  const transactionContext = {
    ...traceparentData,
    metadata: utils.dropUndefinedKeys({
      dynamicSamplingContext: traceparentData && !dynamicSamplingContext ? {} : dynamicSamplingContext,
    }),
  };

  if (!callback) {
    return transactionContext;
  }

  return callback(transactionContext);
}

function createChildSpanOrTransaction(
  hub,
  parentSpan,
  ctx,
) {
  if (!hasTracingEnabled.hasTracingEnabled()) {
    return undefined;
  }
  return parentSpan ? parentSpan.startChild(ctx) : hub.startTransaction(ctx);
}

function normalizeContext(context) {
  const ctx = { ...context };
  // If a name is set and a description is not, set the description to the name.
  if (ctx.name !== undefined && ctx.description === undefined) {
    ctx.description = ctx.name;
  }

  return ctx;
}

exports.continueTrace = continueTrace;
exports.getActiveSpan = getActiveSpan;
exports.startActiveSpan = startActiveSpan;
exports.startInactiveSpan = startInactiveSpan;
exports.startSpan = startSpan;
exports.startSpanManual = startSpanManual;
exports.trace = trace;


},{"../debug-build.js":60,"../hub.js":64,"../utils/hasTracingEnabled.js":93,"@sentry/utils":117}],88:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');
const hub = require('../hub.js');
const dynamicSamplingContext = require('./dynamicSamplingContext.js');
const span = require('./span.js');

/** JSDoc */
class Transaction extends span.Span  {

  /**
   * The reference to the current hub.
   */

  /**
   * This constructor should never be called manually. Those instrumenting tracing should use
   * `Sentry.startTransaction()`, and internal methods should use `hub.startTransaction()`.
   * @internal
   * @hideconstructor
   * @hidden
   */
   constructor(transactionContext, hub$1) {
    super(transactionContext);
    // We need to delete description since it's set by the Span class constructor
    // but not needed for transactions.
    delete this.description;

    this._measurements = {};
    this._contexts = {};

    this._hub = hub$1 || hub.getCurrentHub();

    this._name = transactionContext.name || '';

    this.metadata = {
      source: 'custom',
      ...transactionContext.metadata,
      spanMetadata: {},
    };

    this._trimEnd = transactionContext.trimEnd;

    // this is because transactions are also spans, and spans have a transaction pointer
    this.transaction = this;

    // If Dynamic Sampling Context is provided during the creation of the transaction, we freeze it as it usually means
    // there is incoming Dynamic Sampling Context. (Either through an incoming request, a baggage meta-tag, or other means)
    const incomingDynamicSamplingContext = this.metadata.dynamicSamplingContext;
    if (incomingDynamicSamplingContext) {
      // We shallow copy this in case anything writes to the original reference of the passed in `dynamicSamplingContext`
      this._frozenDynamicSamplingContext = { ...incomingDynamicSamplingContext };
    }
  }

  /** Getter for `name` property */
   get name() {
    return this._name;
  }

  /** Setter for `name` property, which also sets `source` as custom */
   set name(newName) {
    this.setName(newName);
  }

  /**
   * JSDoc
   */
   setName(name, source = 'custom') {
    this._name = name;
    this.metadata.source = source;
  }

  /**
   * Attaches SpanRecorder to the span itself
   * @param maxlen maximum number of spans that can be recorded
   */
   initSpanRecorder(maxlen = 1000) {
    if (!this.spanRecorder) {
      this.spanRecorder = new span.SpanRecorder(maxlen);
    }
    this.spanRecorder.add(this);
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
  }

  /**
   * @inheritDoc
   */
   setMeasurement(name, value, unit = '') {
    this._measurements[name] = { value, unit };
  }

  /**
   * @inheritDoc
   */
   setMetadata(newMetadata) {
    this.metadata = { ...this.metadata, ...newMetadata };
  }

  /**
   * @inheritDoc
   */
   finish(endTimestamp) {
    const transaction = this._finishTransaction(endTimestamp);
    if (!transaction) {
      return undefined;
    }
    return this._hub.captureEvent(transaction);
  }

  /**
   * @inheritDoc
   */
   toContext() {
    const spanContext = super.toContext();

    return utils.dropUndefinedKeys({
      ...spanContext,
      name: this.name,
      trimEnd: this._trimEnd,
    });
  }

  /**
   * @inheritDoc
   */
   updateWithContext(transactionContext) {
    super.updateWithContext(transactionContext);

    this.name = transactionContext.name || '';

    this._trimEnd = transactionContext.trimEnd;

    return this;
  }

  /**
   * @inheritdoc
   *
   * @experimental
   */
   getDynamicSamplingContext() {
    if (this._frozenDynamicSamplingContext) {
      return this._frozenDynamicSamplingContext;
    }

    const hub$1 = this._hub || hub.getCurrentHub();
    const client = hub$1.getClient();

    if (!client) return {};

    const scope = hub$1.getScope();
    const dsc = dynamicSamplingContext.getDynamicSamplingContextFromClient(this.traceId, client, scope);

    const maybeSampleRate = this.metadata.sampleRate;
    if (maybeSampleRate !== undefined) {
      dsc.sample_rate = `${maybeSampleRate}`;
    }

    // We don't want to have a transaction name in the DSC if the source is "url" because URLs might contain PII
    const source = this.metadata.source;
    if (source && source !== 'url') {
      dsc.transaction = this.name;
    }

    if (this.sampled !== undefined) {
      dsc.sampled = String(this.sampled);
    }

    // Uncomment if we want to make DSC immutable
    // this._frozenDynamicSamplingContext = dsc;

    return dsc;
  }

  /**
   * Override the current hub with a new one.
   * Used if you want another hub to finish the transaction.
   *
   * @internal
   */
   setHub(hub) {
    this._hub = hub;
  }

  /**
   * Finish the transaction & prepare the event to send to Sentry.
   */
   _finishTransaction(endTimestamp) {
    // This transaction is already finished, so we should not flush it again.
    if (this.endTimestamp !== undefined) {
      return undefined;
    }

    if (!this.name) {
      debugBuild.DEBUG_BUILD && utils.logger.warn('Transaction has no name, falling back to `<unlabeled transaction>`.');
      this.name = '<unlabeled transaction>';
    }

    // just sets the end timestamp
    super.finish(endTimestamp);

    const client = this._hub.getClient();
    if (client && client.emit) {
      client.emit('finishTransaction', this);
    }

    if (this.sampled !== true) {
      // At this point if `sampled !== true` we want to discard the transaction.
      debugBuild.DEBUG_BUILD && utils.logger.log('[Tracing] Discarding transaction because its trace was not chosen to be sampled.');

      if (client) {
        client.recordDroppedEvent('sample_rate', 'transaction');
      }

      return undefined;
    }

    const finishedSpans = this.spanRecorder ? this.spanRecorder.spans.filter(s => s !== this && s.endTimestamp) : [];

    if (this._trimEnd && finishedSpans.length > 0) {
      this.endTimestamp = finishedSpans.reduce((prev, current) => {
        if (prev.endTimestamp && current.endTimestamp) {
          return prev.endTimestamp > current.endTimestamp ? prev : current;
        }
        return prev;
      }).endTimestamp;
    }

    const metadata = this.metadata;

    const transaction = {
      contexts: {
        ...this._contexts,
        // We don't want to override trace context
        trace: this.getTraceContext(),
      },
      spans: finishedSpans,
      start_timestamp: this.startTimestamp,
      tags: this.tags,
      timestamp: this.endTimestamp,
      transaction: this.name,
      type: 'transaction',
      sdkProcessingMetadata: {
        ...metadata,
        dynamicSamplingContext: this.getDynamicSamplingContext(),
      },
      ...(metadata.source && {
        transaction_info: {
          source: metadata.source,
        },
      }),
    };

    const hasMeasurements = Object.keys(this._measurements).length > 0;

    if (hasMeasurements) {
      debugBuild.DEBUG_BUILD &&
        utils.logger.log(
          '[Measurements] Adding measurements to transaction',
          JSON.stringify(this._measurements, undefined, 2),
        );
      transaction.measurements = this._measurements;
    }

    debugBuild.DEBUG_BUILD && utils.logger.log(`[Tracing] Finishing ${this.op} transaction: ${this.name}.`);

    return transaction;
  }
}

exports.Transaction = Transaction;


},{"../debug-build.js":60,"../hub.js":64,"./dynamicSamplingContext.js":79,"./span.js":85,"@sentry/utils":117}],89:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const hub = require('../hub.js');

/** Grabs active transaction off scope, if any */
function getActiveTransaction(maybeHub) {
  const hub$1 = maybeHub || hub.getCurrentHub();
  const scope = hub$1.getScope();
  return scope.getTransaction() ;
}

/**
 * The `extractTraceparentData` function and `TRACEPARENT_REGEXP` constant used
 * to be declared in this file. It was later moved into `@sentry/utils` as part of a
 * move to remove `@sentry/tracing` dependencies from `@sentry/node` (`extractTraceparentData`
 * is the only tracing function used by `@sentry/node`).
 *
 * These exports are kept here for backwards compatability's sake.
 *
 * See https://github.com/getsentry/sentry-javascript/issues/4642 for more details.
 *
 * @deprecated Import this function from `@sentry/utils` instead
 */
const extractTraceparentData = utils.extractTraceparentData;

exports.stripUrlQueryAndFragment = utils.stripUrlQueryAndFragment;
exports.extractTraceparentData = extractTraceparentData;
exports.getActiveTransaction = getActiveTransaction;


},{"../hub.js":64,"@sentry/utils":117}],90:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');

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
  buffer = utils.makePromiseBuffer(
    options.bufferSize || DEFAULT_TRANSPORT_BUFFER_SIZE,
  ),
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
            debugBuild.DEBUG_BUILD && utils.logger.warn(`Sentry responded with status code ${response.statusCode} to sent event.`);
          }

          rateLimits = utils.updateRateLimits(rateLimits, response);
          return response;
        },
        error => {
          recordEnvelopeLoss('network_error');
          throw error;
        },
      );

    return buffer.add(requestTask).then(
      result => result,
      error => {
        if (error instanceof utils.SentryError) {
          debugBuild.DEBUG_BUILD && utils.logger.error('Skipped sending event because buffer is full.');
          recordEnvelopeLoss('queue_overflow');
          return utils.resolvedSyncPromise();
        } else {
          throw error;
        }
      },
    );
  }

  // We use this to identifify if the transport is the base transport
  // TODO (v8): Remove this again as we'll no longer need it
  send.__sentry__baseTransport__ = true;

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


},{"../debug-build.js":60,"@sentry/utils":117}],91:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const api = require('../api.js');

/**
 * Gets an event from an envelope.
 *
 * This is only exported for use in the tests
 */
function eventFromEnvelope(env, types) {
  let event;

  utils.forEachEnvelopeItem(env, (item, type) => {
    if (types.includes(type)) {
      event = Array.isArray(item) ? (item )[1] : undefined;
    }
    // bail out if we found an event
    return !!event;
  });

  return event;
}

/**
 * Creates a transport that overrides the release on all events.
 */
function makeOverrideReleaseTransport(
  createTransport,
  release,
) {
  return options => {
    const transport = createTransport(options);

    return {
      send: async (envelope) => {
        const event = eventFromEnvelope(envelope, ['event', 'transaction', 'profile', 'replay_event']);

        if (event) {
          event.release = release;
        }
        return transport.send(envelope);
      },
      flush: timeout => transport.flush(timeout),
    };
  };
}

/**
 * Creates a transport that can send events to different DSNs depending on the envelope contents.
 */
function makeMultiplexedTransport(
  createTransport,
  matcher,
) {
  return options => {
    const fallbackTransport = createTransport(options);
    const otherTransports = {};

    function getTransport(dsn, release) {
      // We create a transport for every unique dsn/release combination as there may be code from multiple releases in
      // use at the same time
      const key = release ? `${dsn}:${release}` : dsn;

      if (!otherTransports[key]) {
        const validatedDsn = utils.dsnFromString(dsn);
        if (!validatedDsn) {
          return undefined;
        }
        const url = api.getEnvelopeEndpointWithUrlEncodedAuth(validatedDsn);

        otherTransports[key] = release
          ? makeOverrideReleaseTransport(createTransport, release)({ ...options, url })
          : createTransport({ ...options, url });
      }

      return otherTransports[key];
    }

    async function send(envelope) {
      function getEvent(types) {
        const eventTypes = types && types.length ? types : ['event'];
        return eventFromEnvelope(envelope, eventTypes);
      }

      const transports = matcher({ envelope, getEvent })
        .map(result => {
          if (typeof result === 'string') {
            return getTransport(result, undefined);
          } else {
            return getTransport(result.dsn, result.release);
          }
        })
        .filter((t) => !!t);

      // If we have no transports to send to, use the fallback transport
      if (transports.length === 0) {
        transports.push(fallbackTransport);
      }

      const results = await Promise.all(transports.map(transport => transport.send(envelope)));

      return results[0];
    }

    async function flush(timeout) {
      const allTransports = [...Object.keys(otherTransports).map(dsn => otherTransports[dsn]), fallbackTransport];
      const results = await Promise.all(allTransports.map(transport => transport.flush(timeout)));
      return results.every(r => r);
    }

    return {
      send,
      flush,
    };
  };
}

exports.eventFromEnvelope = eventFromEnvelope;
exports.makeMultiplexedTransport = makeMultiplexedTransport;


},{"../api.js":56,"@sentry/utils":117}],92:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const debugBuild = require('../debug-build.js');

const MIN_DELAY = 100; // 100 ms
const START_DELAY = 5000; // 5 seconds
const MAX_DELAY = 3.6e6; // 1 hour

function log(msg, error) {
  debugBuild.DEBUG_BUILD && utils.logger.info(`[Offline]: ${msg}`, error);
}

/**
 * Wraps a transport and stores and retries events when they fail to send.
 *
 * @param createTransport The transport to wrap.
 */
function makeOfflineTransport(
  createTransport,
) {
  return options => {
    const transport = createTransport(options);
    const store = options.createStore ? options.createStore(options) : undefined;

    let retryDelay = START_DELAY;
    let flushTimer;

    function shouldQueue(env, error, retryDelay) {
      // We don't queue Session Replay envelopes because they are:
      // - Ordered and Replay relies on the response status to know when they're successfully sent.
      // - Likely to fill the queue quickly and block other events from being sent.
      // We also want to drop client reports because they can be generated when we retry sending events while offline.
      if (utils.envelopeContainsItemType(env, ['replay_event', 'replay_recording', 'client_report'])) {
        return false;
      }

      if (options.shouldStore) {
        return options.shouldStore(env, error, retryDelay);
      }

      return true;
    }

    function flushIn(delay) {
      if (!store) {
        return;
      }

      if (flushTimer) {
        clearTimeout(flushTimer );
      }

      flushTimer = setTimeout(async () => {
        flushTimer = undefined;

        const found = await store.pop();
        if (found) {
          log('Attempting to send previously queued event');
          void send(found).catch(e => {
            log('Failed to retry sending', e);
          });
        }
      }, delay) ;

      // We need to unref the timer in node.js, otherwise the node process never exit.
      if (typeof flushTimer !== 'number' && flushTimer.unref) {
        flushTimer.unref();
      }
    }

    function flushWithBackOff() {
      if (flushTimer) {
        return;
      }

      flushIn(retryDelay);

      retryDelay = Math.min(retryDelay * 2, MAX_DELAY);
    }

    async function send(envelope) {
      try {
        const result = await transport.send(envelope);

        let delay = MIN_DELAY;

        if (result) {
          // If there's a retry-after header, use that as the next delay.
          if (result.headers && result.headers['retry-after']) {
            delay = utils.parseRetryAfterHeader(result.headers['retry-after']);
          } // If we have a server error, return now so we don't flush the queue.
          else if ((result.statusCode || 0) >= 400) {
            return result;
          }
        }

        flushIn(delay);
        retryDelay = START_DELAY;
        return result;
      } catch (e) {
        if (store && (await shouldQueue(envelope, e , retryDelay))) {
          await store.insert(envelope);
          flushWithBackOff();
          log('Error sending. Event queued', e );
          return {};
        } else {
          throw e;
        }
      }
    }

    if (options.flushAtStartup) {
      flushWithBackOff();
    }

    return {
      send,
      flush: t => transport.flush(t),
    };
  };
}

exports.MIN_DELAY = MIN_DELAY;
exports.START_DELAY = START_DELAY;
exports.makeOfflineTransport = makeOfflineTransport;


},{"../debug-build.js":60,"@sentry/utils":117}],93:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const exports$1 = require('../exports.js');

// Treeshakable guard to remove all code related to tracing

/**
 * Determines if tracing is currently enabled.
 *
 * Tracing is enabled when at least one of `tracesSampleRate` and `tracesSampler` is defined in the SDK config.
 */
function hasTracingEnabled(
  maybeOptions,
) {
  if (typeof __SENTRY_TRACING__ === 'boolean' && !__SENTRY_TRACING__) {
    return false;
  }

  const client = exports$1.getClient();
  const options = maybeOptions || (client && client.getOptions());
  return !!options && (options.enableTracing || 'tracesSampleRate' in options || 'tracesSampler' in options);
}

exports.hasTracingEnabled = hasTracingEnabled;


},{"../exports.js":63}],94:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Checks whether given url points to Sentry server
 * @param url url to verify
 */
function isSentryRequestUrl(url, hub) {
  const client = hub.getClient();
  const dsn = client && client.getDsn();
  const tunnel = client && client.getOptions().tunnel;

  return checkDsn(url, dsn) || checkTunnel(url, tunnel);
}

function checkTunnel(url, tunnel) {
  if (!tunnel) {
    return false;
  }

  return removeTrailingSlash(url) === removeTrailingSlash(tunnel);
}

function checkDsn(url, dsn) {
  return dsn ? url.includes(dsn.host) : false;
}

function removeTrailingSlash(str) {
  return str[str.length - 1] === '/' ? str.slice(0, -1) : str;
}

exports.isSentryRequestUrl = isSentryRequestUrl;


},{}],95:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const utils = require('@sentry/utils');
const constants = require('../constants.js');
const eventProcessors = require('../eventProcessors.js');
const scope = require('../scope.js');

/**
 * This type makes sure that we get either a CaptureContext, OR an EventHint.
 * It does not allow mixing them, which could lead to unexpected outcomes, e.g. this is disallowed:
 * { user: { id: '123' }, mechanism: { handled: false } }
 */

/**
 * Adds common information to events.
 *
 * The information includes release and environment from `options`,
 * breadcrumbs and context (extra, tags and user) from the scope.
 *
 * Information that is already present in the event is never overwritten. For
 * nested objects, such as the context, keys are merged.
 *
 * Note: This also triggers callbacks for `addGlobalEventProcessor`, but not `beforeSend`.
 *
 * @param event The original event.
 * @param hint May contain additional information about the original exception.
 * @param scope A scope containing event metadata.
 * @returns A new event with more information.
 * @hidden
 */
function prepareEvent(
  options,
  event,
  hint,
  scope$1,
  client,
) {
  const { normalizeDepth = 3, normalizeMaxBreadth = 1000 } = options;
  const prepared = {
    ...event,
    event_id: event.event_id || hint.event_id || utils.uuid4(),
    timestamp: event.timestamp || utils.dateTimestampInSeconds(),
  };
  const integrations = hint.integrations || options.integrations.map(i => i.name);

  applyClientOptions(prepared, options);
  applyIntegrationsMetadata(prepared, integrations);

  // Only put debug IDs onto frames for error events.
  if (event.type === undefined) {
    applyDebugIds(prepared, options.stackParser);
  }

  // If we have scope given to us, use it as the base for further modifications.
  // This allows us to prevent unnecessary copying of data if `captureContext` is not provided.
  let finalScope = scope$1;
  if (hint.captureContext) {
    finalScope = scope.Scope.clone(finalScope).update(hint.captureContext);
  }

  if (hint.mechanism) {
    utils.addExceptionMechanism(prepared, hint.mechanism);
  }

  // We prepare the result here with a resolved Event.
  let result = utils.resolvedSyncPromise(prepared);

  const clientEventProcessors = client && client.getEventProcessors ? client.getEventProcessors() : [];

  // This should be the last thing called, since we want that
  // {@link Hub.addEventProcessor} gets the finished prepared event.
  //
  // We need to check for the existence of `finalScope.getAttachments`
  // because `getAttachments` can be undefined if users are using an older version
  // of `@sentry/core` that does not have the `getAttachments` method.
  // See: https://github.com/getsentry/sentry-javascript/issues/5229
  if (finalScope) {
    // Collect attachments from the hint and scope
    if (finalScope.getAttachments) {
      const attachments = [...(hint.attachments || []), ...finalScope.getAttachments()];

      if (attachments.length) {
        hint.attachments = attachments;
      }
    }

    // In case we have a hub we reassign it.
    result = finalScope.applyToEvent(prepared, hint, clientEventProcessors);
  } else {
    // Apply client & global event processors even if there is no scope
    // TODO (v8): Update the order to be Global > Client
    result = eventProcessors.notifyEventProcessors(
      [
        ...clientEventProcessors,
        // eslint-disable-next-line deprecation/deprecation
        ...eventProcessors.getGlobalEventProcessors(),
      ],
      prepared,
      hint,
    );
  }

  return result.then(evt => {
    if (evt) {
      // We apply the debug_meta field only after all event processors have ran, so that if any event processors modified
      // file names (e.g.the RewriteFrames integration) the filename -> debug ID relationship isn't destroyed.
      // This should not cause any PII issues, since we're only moving data that is already on the event and not adding
      // any new data
      applyDebugMeta(evt);
    }

    if (typeof normalizeDepth === 'number' && normalizeDepth > 0) {
      return normalizeEvent(evt, normalizeDepth, normalizeMaxBreadth);
    }
    return evt;
  });
}

/**
 *  Enhances event using the client configuration.
 *  It takes care of all "static" values like environment, release and `dist`,
 *  as well as truncating overly long values.
 * @param event event instance to be enhanced
 */
function applyClientOptions(event, options) {
  const { environment, release, dist, maxValueLength = 250 } = options;

  if (!('environment' in event)) {
    event.environment = 'environment' in options ? environment : constants.DEFAULT_ENVIRONMENT;
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

const debugIdStackParserCache = new WeakMap();

/**
 * Puts debug IDs into the stack frames of an error event.
 */
function applyDebugIds(event, stackParser) {
  const debugIdMap = utils.GLOBAL_OBJ._sentryDebugIds;

  if (!debugIdMap) {
    return;
  }

  let debugIdStackFramesCache;
  const cachedDebugIdStackFrameCache = debugIdStackParserCache.get(stackParser);
  if (cachedDebugIdStackFrameCache) {
    debugIdStackFramesCache = cachedDebugIdStackFrameCache;
  } else {
    debugIdStackFramesCache = new Map();
    debugIdStackParserCache.set(stackParser, debugIdStackFramesCache);
  }

  // Build a map of filename -> debug_id
  const filenameDebugIdMap = Object.keys(debugIdMap).reduce((acc, debugIdStackTrace) => {
    let parsedStack;
    const cachedParsedStack = debugIdStackFramesCache.get(debugIdStackTrace);
    if (cachedParsedStack) {
      parsedStack = cachedParsedStack;
    } else {
      parsedStack = stackParser(debugIdStackTrace);
      debugIdStackFramesCache.set(debugIdStackTrace, parsedStack);
    }

    for (let i = parsedStack.length - 1; i >= 0; i--) {
      const stackFrame = parsedStack[i];
      if (stackFrame.filename) {
        acc[stackFrame.filename] = debugIdMap[debugIdStackTrace];
        break;
      }
    }
    return acc;
  }, {});

  try {
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    event.exception.values.forEach(exception => {
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      exception.stacktrace.frames.forEach(frame => {
        if (frame.filename) {
          frame.debug_id = filenameDebugIdMap[frame.filename];
        }
      });
    });
  } catch (e) {
    // To save bundle size we're just try catching here instead of checking for the existence of all the different objects.
  }
}

/**
 * Moves debug IDs from the stack frames of an error event into the debug_meta field.
 */
function applyDebugMeta(event) {
  // Extract debug IDs and filenames from the stack frames on the event.
  const filenameDebugIdMap = {};
  try {
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    event.exception.values.forEach(exception => {
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      exception.stacktrace.frames.forEach(frame => {
        if (frame.debug_id) {
          if (frame.abs_path) {
            filenameDebugIdMap[frame.abs_path] = frame.debug_id;
          } else if (frame.filename) {
            filenameDebugIdMap[frame.filename] = frame.debug_id;
          }
          delete frame.debug_id;
        }
      });
    });
  } catch (e) {
    // To save bundle size we're just try catching here instead of checking for the existence of all the different objects.
  }

  if (Object.keys(filenameDebugIdMap).length === 0) {
    return;
  }

  // Fill debug_meta information
  event.debug_meta = event.debug_meta || {};
  event.debug_meta.images = event.debug_meta.images || [];
  const images = event.debug_meta.images;
  Object.keys(filenameDebugIdMap).forEach(filename => {
    images.push({
      type: 'sourcemap',
      code_file: filename,
      debug_id: filenameDebugIdMap[filename],
    });
  });
}

/**
 * This function adds all used integrations to the SDK info in the event.
 * @param event The event that will be filled with all integrations.
 */
function applyIntegrationsMetadata(event, integrationNames) {
  if (integrationNames.length > 0) {
    event.sdk = event.sdk || {};
    event.sdk.integrations = [...(event.sdk.integrations || []), ...integrationNames];
  }
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
function normalizeEvent(event, depth, maxBreadth) {
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
 * Parse either an `EventHint` directly, or convert a `CaptureContext` to an `EventHint`.
 * This is used to allow to update method signatures that used to accept a `CaptureContext` but should now accept an `EventHint`.
 */
function parseEventHintOrCaptureContext(
  hint,
) {
  if (!hint) {
    return undefined;
  }

  // If you pass a Scope or `() => Scope` as CaptureContext, we just return this as captureContext
  if (hintIsScopeOrFunction(hint)) {
    return { captureContext: hint };
  }

  if (hintIsScopeContext(hint)) {
    return {
      captureContext: hint,
    };
  }

  return hint;
}

function hintIsScopeOrFunction(
  hint,
) {
  return hint instanceof scope.Scope || typeof hint === 'function';
}

const captureContextKeys = [
  'user',
  'level',
  'extra',
  'contexts',
  'tags',
  'fingerprint',
  'requestSession',
  'propagationContext',
] ;

function hintIsScopeContext(hint) {
  return Object.keys(hint).some(key => captureContextKeys.includes(key ));
}

exports.applyDebugIds = applyDebugIds;
exports.applyDebugMeta = applyDebugMeta;
exports.parseEventHintOrCaptureContext = parseEventHintOrCaptureContext;
exports.prepareEvent = prepareEvent;


},{"../constants.js":59,"../eventProcessors.js":62,"../scope.js":74,"@sentry/utils":117}],96:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const SDK_VERSION = '7.85.0';

exports.SDK_VERSION = SDK_VERSION;


},{}],97:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const core = require('@sentry/core');
const utils = require('@sentry/utils');
const tracing = require('@sentry-internal/tracing');

// exporting a separate copy of `WINDOW` rather than exporting the one from `@sentry/browser`
// prevents the browser package from being bundled in the CDN bundle, and avoids a
// circular dependency between the browser and replay packages should `@sentry/browser` import
// from `@sentry/replay` in the future
const WINDOW = utils.GLOBAL_OBJ ;

const REPLAY_SESSION_KEY = 'sentryReplaySession';
const REPLAY_EVENT_NAME = 'replay_event';
const UNABLE_TO_SEND_REPLAY = 'Unable to send Replay';

// The idle limit for a session after which recording is paused.
const SESSION_IDLE_PAUSE_DURATION = 300000; // 5 minutes in ms

// The idle limit for a session after which the session expires.
const SESSION_IDLE_EXPIRE_DURATION = 900000; // 15 minutes in ms

/** Default flush delays */
const DEFAULT_FLUSH_MIN_DELAY = 5000;
// XXX: Temp fix for our debounce logic where `maxWait` would never occur if it
// was the same as `wait`
const DEFAULT_FLUSH_MAX_DELAY = 5500;

/* How long to wait for error checkouts */
const BUFFER_CHECKOUT_TIME = 60000;

const RETRY_BASE_INTERVAL = 5000;
const RETRY_MAX_COUNT = 3;

/* The max (uncompressed) size in bytes of a network body. Any body larger than this will be truncated. */
const NETWORK_BODY_MAX_SIZE = 150000;

/* The max size of a single console arg that is captured. Any arg larger than this will be truncated. */
const CONSOLE_ARG_MAX_SIZE = 5000;

/* Min. time to wait before we consider something a slow click. */
const SLOW_CLICK_THRESHOLD = 3000;
/* For scroll actions after a click, we only look for a very short time period to detect programmatic scrolling. */
const SLOW_CLICK_SCROLL_TIMEOUT = 300;

/** When encountering a total segment size exceeding this size, stop the replay (as we cannot properly ingest it). */
const REPLAY_MAX_EVENT_BUFFER_SIZE = 20000000; // ~20MB

/** Replays must be min. 5s long before we send them. */
const MIN_REPLAY_DURATION = 4999;
/* The max. allowed value that the minReplayDuration can be set to. */
const MIN_REPLAY_DURATION_LIMIT = 15000;

/** The max. length of a replay. */
const MAX_REPLAY_DURATION = 3600000; // 60 minutes in ms;

var NodeType$1;
(function (NodeType) {
    NodeType[NodeType["Document"] = 0] = "Document";
    NodeType[NodeType["DocumentType"] = 1] = "DocumentType";
    NodeType[NodeType["Element"] = 2] = "Element";
    NodeType[NodeType["Text"] = 3] = "Text";
    NodeType[NodeType["CDATA"] = 4] = "CDATA";
    NodeType[NodeType["Comment"] = 5] = "Comment";
})(NodeType$1 || (NodeType$1 = {}));

function isElement$1(n) {
    return n.nodeType === n.ELEMENT_NODE;
}
function isShadowRoot(n) {
    const host = n === null || n === void 0 ? void 0 : n.host;
    return Boolean((host === null || host === void 0 ? void 0 : host.shadowRoot) === n);
}
function isNativeShadowDom(shadowRoot) {
    return Object.prototype.toString.call(shadowRoot) === '[object ShadowRoot]';
}
function fixBrowserCompatibilityIssuesInCSS(cssText) {
    if (cssText.includes(' background-clip: text;') &&
        !cssText.includes(' -webkit-background-clip: text;')) {
        cssText = cssText.replace(' background-clip: text;', ' -webkit-background-clip: text; background-clip: text;');
    }
    return cssText;
}
function escapeImportStatement(rule) {
    const { cssText } = rule;
    if (cssText.split('"').length < 3)
        return cssText;
    const statement = ['@import', `url(${JSON.stringify(rule.href)})`];
    if (rule.layerName === '') {
        statement.push(`layer`);
    }
    else if (rule.layerName) {
        statement.push(`layer(${rule.layerName})`);
    }
    if (rule.supportsText) {
        statement.push(`supports(${rule.supportsText})`);
    }
    if (rule.media.length) {
        statement.push(rule.media.mediaText);
    }
    return statement.join(' ') + ';';
}
function stringifyStylesheet(s) {
    try {
        const rules = s.rules || s.cssRules;
        return rules
            ? fixBrowserCompatibilityIssuesInCSS(Array.from(rules, stringifyRule).join(''))
            : null;
    }
    catch (error) {
        return null;
    }
}
function stringifyRule(rule) {
    let importStringified;
    if (isCSSImportRule(rule)) {
        try {
            importStringified =
                stringifyStylesheet(rule.styleSheet) ||
                    escapeImportStatement(rule);
        }
        catch (error) {
        }
    }
    else if (isCSSStyleRule(rule) && rule.selectorText.includes(':')) {
        return fixSafariColons(rule.cssText);
    }
    return importStringified || rule.cssText;
}
function fixSafariColons(cssStringified) {
    const regex = /(\[(?:[\w-]+)[^\\])(:(?:[\w-]+)\])/gm;
    return cssStringified.replace(regex, '$1\\$2');
}
function isCSSImportRule(rule) {
    return 'styleSheet' in rule;
}
function isCSSStyleRule(rule) {
    return 'selectorText' in rule;
}
class Mirror {
    constructor() {
        this.idNodeMap = new Map();
        this.nodeMetaMap = new WeakMap();
    }
    getId(n) {
        var _a;
        if (!n)
            return -1;
        const id = (_a = this.getMeta(n)) === null || _a === void 0 ? void 0 : _a.id;
        return id !== null && id !== void 0 ? id : -1;
    }
    getNode(id) {
        return this.idNodeMap.get(id) || null;
    }
    getIds() {
        return Array.from(this.idNodeMap.keys());
    }
    getMeta(n) {
        return this.nodeMetaMap.get(n) || null;
    }
    removeNodeFromMap(n) {
        const id = this.getId(n);
        this.idNodeMap.delete(id);
        if (n.childNodes) {
            n.childNodes.forEach((childNode) => this.removeNodeFromMap(childNode));
        }
    }
    has(id) {
        return this.idNodeMap.has(id);
    }
    hasNode(node) {
        return this.nodeMetaMap.has(node);
    }
    add(n, meta) {
        const id = meta.id;
        this.idNodeMap.set(id, n);
        this.nodeMetaMap.set(n, meta);
    }
    replace(id, n) {
        const oldNode = this.getNode(id);
        if (oldNode) {
            const meta = this.nodeMetaMap.get(oldNode);
            if (meta)
                this.nodeMetaMap.set(n, meta);
        }
        this.idNodeMap.set(id, n);
    }
    reset() {
        this.idNodeMap = new Map();
        this.nodeMetaMap = new WeakMap();
    }
}
function createMirror() {
    return new Mirror();
}
function shouldMaskInput({ maskInputOptions, tagName, type, }) {
    if (tagName === 'OPTION') {
        tagName = 'SELECT';
    }
    return Boolean(maskInputOptions[tagName.toLowerCase()] ||
        (type && maskInputOptions[type]) ||
        type === 'password' ||
        (tagName === 'INPUT' && !type && maskInputOptions['text']));
}
function maskInputValue({ isMasked, element, value, maskInputFn, }) {
    let text = value || '';
    if (!isMasked) {
        return text;
    }
    if (maskInputFn) {
        text = maskInputFn(text, element);
    }
    return '*'.repeat(text.length);
}
function toLowerCase(str) {
    return str.toLowerCase();
}
function toUpperCase(str) {
    return str.toUpperCase();
}
const ORIGINAL_ATTRIBUTE_NAME = '__rrweb_original__';
function is2DCanvasBlank(canvas) {
    const ctx = canvas.getContext('2d');
    if (!ctx)
        return true;
    const chunkSize = 50;
    for (let x = 0; x < canvas.width; x += chunkSize) {
        for (let y = 0; y < canvas.height; y += chunkSize) {
            const getImageData = ctx.getImageData;
            const originalGetImageData = ORIGINAL_ATTRIBUTE_NAME in getImageData
                ? getImageData[ORIGINAL_ATTRIBUTE_NAME]
                : getImageData;
            const pixelBuffer = new Uint32Array(originalGetImageData.call(ctx, x, y, Math.min(chunkSize, canvas.width - x), Math.min(chunkSize, canvas.height - y)).data.buffer);
            if (pixelBuffer.some((pixel) => pixel !== 0))
                return false;
        }
    }
    return true;
}
function getInputType(element) {
    const type = element.type;
    return element.hasAttribute('data-rr-is-password')
        ? 'password'
        : type
            ?
                toLowerCase(type)
            : null;
}
function getInputValue(el, tagName, type) {
    if (tagName === 'INPUT' && (type === 'radio' || type === 'checkbox')) {
        return el.getAttribute('value') || '';
    }
    return el.value;
}

let _id = 1;
const tagNameRegex = new RegExp('[^a-z0-9-_:]');
const IGNORED_NODE = -2;
function genId() {
    return _id++;
}
function getValidTagName(element) {
    if (element instanceof HTMLFormElement) {
        return 'form';
    }
    const processedTagName = toLowerCase(element.tagName);
    if (tagNameRegex.test(processedTagName)) {
        return 'div';
    }
    return processedTagName;
}
function extractOrigin(url) {
    let origin = '';
    if (url.indexOf('//') > -1) {
        origin = url.split('/').slice(0, 3).join('/');
    }
    else {
        origin = url.split('/')[0];
    }
    origin = origin.split('?')[0];
    return origin;
}
let canvasService;
let canvasCtx;
const URL_IN_CSS_REF = /url\((?:(')([^']*)'|(")(.*?)"|([^)]*))\)/gm;
const URL_PROTOCOL_MATCH = /^(?:[a-z+]+:)?\/\//i;
const URL_WWW_MATCH = /^www\..*/i;
const DATA_URI = /^(data:)([^,]*),(.*)/i;
function absoluteToStylesheet(cssText, href) {
    return (cssText || '').replace(URL_IN_CSS_REF, (origin, quote1, path1, quote2, path2, path3) => {
        const filePath = path1 || path2 || path3;
        const maybeQuote = quote1 || quote2 || '';
        if (!filePath) {
            return origin;
        }
        if (URL_PROTOCOL_MATCH.test(filePath) || URL_WWW_MATCH.test(filePath)) {
            return `url(${maybeQuote}${filePath}${maybeQuote})`;
        }
        if (DATA_URI.test(filePath)) {
            return `url(${maybeQuote}${filePath}${maybeQuote})`;
        }
        if (filePath[0] === '/') {
            return `url(${maybeQuote}${extractOrigin(href) + filePath}${maybeQuote})`;
        }
        const stack = href.split('/');
        const parts = filePath.split('/');
        stack.pop();
        for (const part of parts) {
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
        return `url(${maybeQuote}${stack.join('/')}${maybeQuote})`;
    });
}
const SRCSET_NOT_SPACES = /^[^ \t\n\r\u000c]+/;
const SRCSET_COMMAS_OR_SPACES = /^[, \t\n\r\u000c]+/;
function getAbsoluteSrcsetString(doc, attributeValue) {
    if (attributeValue.trim() === '') {
        return attributeValue;
    }
    let pos = 0;
    function collectCharacters(regEx) {
        let chars;
        const match = regEx.exec(attributeValue.substring(pos));
        if (match) {
            chars = match[0];
            pos += chars.length;
            return chars;
        }
        return '';
    }
    const output = [];
    while (true) {
        collectCharacters(SRCSET_COMMAS_OR_SPACES);
        if (pos >= attributeValue.length) {
            break;
        }
        let url = collectCharacters(SRCSET_NOT_SPACES);
        if (url.slice(-1) === ',') {
            url = absoluteToDoc(doc, url.substring(0, url.length - 1));
            output.push(url);
        }
        else {
            let descriptorsStr = '';
            url = absoluteToDoc(doc, url);
            let inParens = false;
            while (true) {
                const c = attributeValue.charAt(pos);
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
    const a = doc.createElement('a');
    a.href = attributeValue;
    return a.href;
}
function isSVGElement(el) {
    return Boolean(el.tagName === 'svg' || el.ownerSVGElement);
}
function getHref() {
    const a = document.createElement('a');
    a.href = '';
    return a.href;
}
function transformAttribute(doc, tagName, name, value, element, maskAttributeFn) {
    if (!value) {
        return value;
    }
    if (name === 'src' ||
        (name === 'href' && !(tagName === 'use' && value[0] === '#'))) {
        return absoluteToDoc(doc, value);
    }
    else if (name === 'xlink:href' && value[0] !== '#') {
        return absoluteToDoc(doc, value);
    }
    else if (name === 'background' &&
        (tagName === 'table' || tagName === 'td' || tagName === 'th')) {
        return absoluteToDoc(doc, value);
    }
    else if (name === 'srcset') {
        return getAbsoluteSrcsetString(doc, value);
    }
    else if (name === 'style') {
        return absoluteToStylesheet(value, getHref());
    }
    else if (tagName === 'object' && name === 'data') {
        return absoluteToDoc(doc, value);
    }
    if (typeof maskAttributeFn === 'function') {
        return maskAttributeFn(name, value, element);
    }
    return value;
}
function ignoreAttribute(tagName, name, _value) {
    return (tagName === 'video' || tagName === 'audio') && name === 'autoplay';
}
function _isBlockedElement(element, blockClass, blockSelector, unblockSelector) {
    try {
        if (unblockSelector && element.matches(unblockSelector)) {
            return false;
        }
        if (typeof blockClass === 'string') {
            if (element.classList.contains(blockClass)) {
                return true;
            }
        }
        else {
            for (let eIndex = element.classList.length; eIndex--;) {
                const className = element.classList[eIndex];
                if (blockClass.test(className)) {
                    return true;
                }
            }
        }
        if (blockSelector) {
            return element.matches(blockSelector);
        }
    }
    catch (e) {
    }
    return false;
}
function elementClassMatchesRegex(el, regex) {
    for (let eIndex = el.classList.length; eIndex--;) {
        const className = el.classList[eIndex];
        if (regex.test(className)) {
            return true;
        }
    }
    return false;
}
function distanceToMatch(node, matchPredicate, limit = Infinity, distance = 0) {
    if (!node)
        return -1;
    if (node.nodeType !== node.ELEMENT_NODE)
        return -1;
    if (distance > limit)
        return -1;
    if (matchPredicate(node))
        return distance;
    return distanceToMatch(node.parentNode, matchPredicate, limit, distance + 1);
}
function createMatchPredicate(className, selector) {
    return (node) => {
        const el = node;
        if (el === null)
            return false;
        if (className) {
            if (typeof className === 'string') {
                if (el.matches(`.${className}`))
                    return true;
            }
            else if (elementClassMatchesRegex(el, className)) {
                return true;
            }
        }
        if (selector && el.matches(selector))
            return true;
        return false;
    };
}
function needMaskingText(node, maskTextClass, maskTextSelector, unmaskTextClass, unmaskTextSelector, maskAllText) {
    try {
        const el = node.nodeType === node.ELEMENT_NODE
            ? node
            : node.parentElement;
        if (el === null)
            return false;
        let maskDistance = -1;
        let unmaskDistance = -1;
        if (maskAllText) {
            unmaskDistance = distanceToMatch(el, createMatchPredicate(unmaskTextClass, unmaskTextSelector));
            if (unmaskDistance < 0) {
                return true;
            }
            maskDistance = distanceToMatch(el, createMatchPredicate(maskTextClass, maskTextSelector), unmaskDistance >= 0 ? unmaskDistance : Infinity);
        }
        else {
            maskDistance = distanceToMatch(el, createMatchPredicate(maskTextClass, maskTextSelector));
            if (maskDistance < 0) {
                return false;
            }
            unmaskDistance = distanceToMatch(el, createMatchPredicate(unmaskTextClass, unmaskTextSelector), maskDistance >= 0 ? maskDistance : Infinity);
        }
        return maskDistance >= 0
            ? unmaskDistance >= 0
                ? maskDistance <= unmaskDistance
                : true
            : unmaskDistance >= 0
                ? false
                : !!maskAllText;
    }
    catch (e) {
    }
    return !!maskAllText;
}
function onceIframeLoaded(iframeEl, listener, iframeLoadTimeout) {
    const win = iframeEl.contentWindow;
    if (!win) {
        return;
    }
    let fired = false;
    let readyState;
    try {
        readyState = win.document.readyState;
    }
    catch (error) {
        return;
    }
    if (readyState !== 'complete') {
        const timer = setTimeout(() => {
            if (!fired) {
                listener();
                fired = true;
            }
        }, iframeLoadTimeout);
        iframeEl.addEventListener('load', () => {
            clearTimeout(timer);
            fired = true;
            listener();
        });
        return;
    }
    const blankUrl = 'about:blank';
    if (win.location.href !== blankUrl ||
        iframeEl.src === blankUrl ||
        iframeEl.src === '') {
        setTimeout(listener, 0);
        return iframeEl.addEventListener('load', listener);
    }
    iframeEl.addEventListener('load', listener);
}
function onceStylesheetLoaded(link, listener, styleSheetLoadTimeout) {
    let fired = false;
    let styleSheetLoaded;
    try {
        styleSheetLoaded = link.sheet;
    }
    catch (error) {
        return;
    }
    if (styleSheetLoaded)
        return;
    const timer = setTimeout(() => {
        if (!fired) {
            listener();
            fired = true;
        }
    }, styleSheetLoadTimeout);
    link.addEventListener('load', () => {
        clearTimeout(timer);
        fired = true;
        listener();
    });
}
function serializeNode(n, options) {
    const { doc, mirror, blockClass, blockSelector, unblockSelector, maskAllText, maskAttributeFn, maskTextClass, unmaskTextClass, maskTextSelector, unmaskTextSelector, inlineStylesheet, maskInputOptions = {}, maskTextFn, maskInputFn, dataURLOptions = {}, inlineImages, recordCanvas, keepIframeSrcFn, newlyAddedElement = false, } = options;
    const rootId = getRootId(doc, mirror);
    switch (n.nodeType) {
        case n.DOCUMENT_NODE:
            if (n.compatMode !== 'CSS1Compat') {
                return {
                    type: NodeType$1.Document,
                    childNodes: [],
                    compatMode: n.compatMode,
                };
            }
            else {
                return {
                    type: NodeType$1.Document,
                    childNodes: [],
                };
            }
        case n.DOCUMENT_TYPE_NODE:
            return {
                type: NodeType$1.DocumentType,
                name: n.name,
                publicId: n.publicId,
                systemId: n.systemId,
                rootId,
            };
        case n.ELEMENT_NODE:
            return serializeElementNode(n, {
                doc,
                blockClass,
                blockSelector,
                unblockSelector,
                inlineStylesheet,
                maskAttributeFn,
                maskInputOptions,
                maskInputFn,
                dataURLOptions,
                inlineImages,
                recordCanvas,
                keepIframeSrcFn,
                newlyAddedElement,
                rootId,
                maskAllText,
                maskTextClass,
                unmaskTextClass,
                maskTextSelector,
                unmaskTextSelector,
            });
        case n.TEXT_NODE:
            return serializeTextNode(n, {
                maskAllText,
                maskTextClass,
                unmaskTextClass,
                maskTextSelector,
                unmaskTextSelector,
                maskTextFn,
                maskInputOptions,
                maskInputFn,
                rootId,
            });
        case n.CDATA_SECTION_NODE:
            return {
                type: NodeType$1.CDATA,
                textContent: '',
                rootId,
            };
        case n.COMMENT_NODE:
            return {
                type: NodeType$1.Comment,
                textContent: n.textContent || '',
                rootId,
            };
        default:
            return false;
    }
}
function getRootId(doc, mirror) {
    if (!mirror.hasNode(doc))
        return undefined;
    const docId = mirror.getId(doc);
    return docId === 1 ? undefined : docId;
}
function serializeTextNode(n, options) {
    var _a;
    const { maskAllText, maskTextClass, unmaskTextClass, maskTextSelector, unmaskTextSelector, maskTextFn, maskInputOptions, maskInputFn, rootId, } = options;
    const parentTagName = n.parentNode && n.parentNode.tagName;
    let textContent = n.textContent;
    const isStyle = parentTagName === 'STYLE' ? true : undefined;
    const isScript = parentTagName === 'SCRIPT' ? true : undefined;
    const isTextarea = parentTagName === 'TEXTAREA' ? true : undefined;
    if (isStyle && textContent) {
        try {
            if (n.nextSibling || n.previousSibling) {
            }
            else if ((_a = n.parentNode.sheet) === null || _a === void 0 ? void 0 : _a.cssRules) {
                textContent = stringifyStylesheet(n.parentNode.sheet);
            }
        }
        catch (err) {
            console.warn(`Cannot get CSS styles from text's parentNode. Error: ${err}`, n);
        }
        textContent = absoluteToStylesheet(textContent, getHref());
    }
    if (isScript) {
        textContent = 'SCRIPT_PLACEHOLDER';
    }
    const forceMask = needMaskingText(n, maskTextClass, maskTextSelector, unmaskTextClass, unmaskTextSelector, maskAllText);
    if (!isStyle && !isScript && !isTextarea && textContent && forceMask) {
        textContent = maskTextFn
            ? maskTextFn(textContent)
            : textContent.replace(/[\S]/g, '*');
    }
    if (isTextarea && textContent && (maskInputOptions.textarea || forceMask)) {
        textContent = maskInputFn
            ? maskInputFn(textContent, n.parentNode)
            : textContent.replace(/[\S]/g, '*');
    }
    if (parentTagName === 'OPTION' && textContent) {
        const isInputMasked = shouldMaskInput({
            type: null,
            tagName: parentTagName,
            maskInputOptions,
        });
        textContent = maskInputValue({
            isMasked: needMaskingText(n, maskTextClass, maskTextSelector, unmaskTextClass, unmaskTextSelector, isInputMasked),
            element: n,
            value: textContent,
            maskInputFn,
        });
    }
    return {
        type: NodeType$1.Text,
        textContent: textContent || '',
        isStyle,
        rootId,
    };
}
function serializeElementNode(n, options) {
    const { doc, blockClass, blockSelector, unblockSelector, inlineStylesheet, maskInputOptions = {}, maskAttributeFn, maskInputFn, dataURLOptions = {}, inlineImages, recordCanvas, keepIframeSrcFn, newlyAddedElement = false, rootId, maskAllText, maskTextClass, unmaskTextClass, maskTextSelector, unmaskTextSelector, } = options;
    const needBlock = _isBlockedElement(n, blockClass, blockSelector, unblockSelector);
    const tagName = getValidTagName(n);
    let attributes = {};
    const len = n.attributes.length;
    for (let i = 0; i < len; i++) {
        const attr = n.attributes[i];
        if (!ignoreAttribute(tagName, attr.name, attr.value)) {
            attributes[attr.name] = transformAttribute(doc, tagName, toLowerCase(attr.name), attr.value, n, maskAttributeFn);
        }
    }
    if (tagName === 'link' && inlineStylesheet) {
        const stylesheet = Array.from(doc.styleSheets).find((s) => {
            return s.href === n.href;
        });
        let cssText = null;
        if (stylesheet) {
            cssText = stringifyStylesheet(stylesheet);
        }
        if (cssText) {
            delete attributes.rel;
            delete attributes.href;
            attributes._cssText = absoluteToStylesheet(cssText, stylesheet.href);
        }
    }
    if (tagName === 'style' &&
        n.sheet &&
        !(n.innerText || n.textContent || '').trim().length) {
        const cssText = stringifyStylesheet(n.sheet);
        if (cssText) {
            attributes._cssText = absoluteToStylesheet(cssText, getHref());
        }
    }
    if (tagName === 'input' ||
        tagName === 'textarea' ||
        tagName === 'select' ||
        tagName === 'option') {
        const el = n;
        const type = getInputType(el);
        const value = getInputValue(el, toUpperCase(tagName), type);
        const checked = el.checked;
        if (type !== 'submit' && type !== 'button' && value) {
            const forceMask = needMaskingText(el, maskTextClass, maskTextSelector, unmaskTextClass, unmaskTextSelector, shouldMaskInput({
                type,
                tagName: toUpperCase(tagName),
                maskInputOptions,
            }));
            attributes.value = maskInputValue({
                isMasked: forceMask,
                element: el,
                value,
                maskInputFn,
            });
        }
        if (checked) {
            attributes.checked = checked;
        }
    }
    if (tagName === 'option') {
        if (n.selected && !maskInputOptions['select']) {
            attributes.selected = true;
        }
        else {
            delete attributes.selected;
        }
    }
    if (tagName === 'canvas' && recordCanvas) {
        if (n.__context === '2d') {
            if (!is2DCanvasBlank(n)) {
                attributes.rr_dataURL = n.toDataURL(dataURLOptions.type, dataURLOptions.quality);
            }
        }
        else if (!('__context' in n)) {
            const canvasDataURL = n.toDataURL(dataURLOptions.type, dataURLOptions.quality);
            const blankCanvas = document.createElement('canvas');
            blankCanvas.width = n.width;
            blankCanvas.height = n.height;
            const blankCanvasDataURL = blankCanvas.toDataURL(dataURLOptions.type, dataURLOptions.quality);
            if (canvasDataURL !== blankCanvasDataURL) {
                attributes.rr_dataURL = canvasDataURL;
            }
        }
    }
    if (tagName === 'img' && inlineImages) {
        if (!canvasService) {
            canvasService = doc.createElement('canvas');
            canvasCtx = canvasService.getContext('2d');
        }
        const image = n;
        const oldValue = image.crossOrigin;
        image.crossOrigin = 'anonymous';
        const recordInlineImage = () => {
            image.removeEventListener('load', recordInlineImage);
            try {
                canvasService.width = image.naturalWidth;
                canvasService.height = image.naturalHeight;
                canvasCtx.drawImage(image, 0, 0);
                attributes.rr_dataURL = canvasService.toDataURL(dataURLOptions.type, dataURLOptions.quality);
            }
            catch (err) {
                console.warn(`Cannot inline img src=${image.currentSrc}! Error: ${err}`);
            }
            oldValue
                ? (attributes.crossOrigin = oldValue)
                : image.removeAttribute('crossorigin');
        };
        if (image.complete && image.naturalWidth !== 0)
            recordInlineImage();
        else
            image.addEventListener('load', recordInlineImage);
    }
    if (tagName === 'audio' || tagName === 'video') {
        attributes.rr_mediaState = n.paused
            ? 'paused'
            : 'played';
        attributes.rr_mediaCurrentTime = n.currentTime;
    }
    if (!newlyAddedElement) {
        if (n.scrollLeft) {
            attributes.rr_scrollLeft = n.scrollLeft;
        }
        if (n.scrollTop) {
            attributes.rr_scrollTop = n.scrollTop;
        }
    }
    if (needBlock) {
        const { width, height } = n.getBoundingClientRect();
        attributes = {
            class: attributes.class,
            rr_width: `${width}px`,
            rr_height: `${height}px`,
        };
    }
    if (tagName === 'iframe' && !keepIframeSrcFn(attributes.src)) {
        if (!n.contentDocument) {
            attributes.rr_src = attributes.src;
        }
        delete attributes.src;
    }
    let isCustomElement;
    try {
        if (customElements.get(tagName))
            isCustomElement = true;
    }
    catch (e) {
    }
    return {
        type: NodeType$1.Element,
        tagName,
        attributes,
        childNodes: [],
        isSVG: isSVGElement(n) || undefined,
        needBlock,
        rootId,
        isCustom: isCustomElement,
    };
}
function lowerIfExists(maybeAttr) {
    if (maybeAttr === undefined || maybeAttr === null) {
        return '';
    }
    else {
        return maybeAttr.toLowerCase();
    }
}
function slimDOMExcluded(sn, slimDOMOptions) {
    if (slimDOMOptions.comment && sn.type === NodeType$1.Comment) {
        return true;
    }
    else if (sn.type === NodeType$1.Element) {
        if (slimDOMOptions.script &&
            (sn.tagName === 'script' ||
                (sn.tagName === 'link' &&
                    (sn.attributes.rel === 'preload' ||
                        sn.attributes.rel === 'modulepreload') &&
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
    const { doc, mirror, blockClass, blockSelector, unblockSelector, maskAllText, maskTextClass, unmaskTextClass, maskTextSelector, unmaskTextSelector, skipChild = false, inlineStylesheet = true, maskInputOptions = {}, maskAttributeFn, maskTextFn, maskInputFn, slimDOMOptions, dataURLOptions = {}, inlineImages = false, recordCanvas = false, onSerialize, onIframeLoad, iframeLoadTimeout = 5000, onStylesheetLoad, stylesheetLoadTimeout = 5000, keepIframeSrcFn = () => false, newlyAddedElement = false, } = options;
    let { preserveWhiteSpace = true } = options;
    const _serializedNode = serializeNode(n, {
        doc,
        mirror,
        blockClass,
        blockSelector,
        maskAllText,
        unblockSelector,
        maskTextClass,
        unmaskTextClass,
        maskTextSelector,
        unmaskTextSelector,
        inlineStylesheet,
        maskInputOptions,
        maskAttributeFn,
        maskTextFn,
        maskInputFn,
        dataURLOptions,
        inlineImages,
        recordCanvas,
        keepIframeSrcFn,
        newlyAddedElement,
    });
    if (!_serializedNode) {
        console.warn(n, 'not serialized');
        return null;
    }
    let id;
    if (mirror.hasNode(n)) {
        id = mirror.getId(n);
    }
    else if (slimDOMExcluded(_serializedNode, slimDOMOptions) ||
        (!preserveWhiteSpace &&
            _serializedNode.type === NodeType$1.Text &&
            !_serializedNode.isStyle &&
            !_serializedNode.textContent.replace(/^\s+|\s+$/gm, '').length)) {
        id = IGNORED_NODE;
    }
    else {
        id = genId();
    }
    const serializedNode = Object.assign(_serializedNode, { id });
    mirror.add(n, serializedNode);
    if (id === IGNORED_NODE) {
        return null;
    }
    if (onSerialize) {
        onSerialize(n);
    }
    let recordChild = !skipChild;
    if (serializedNode.type === NodeType$1.Element) {
        recordChild = recordChild && !serializedNode.needBlock;
        delete serializedNode.needBlock;
        const shadowRoot = n.shadowRoot;
        if (shadowRoot && isNativeShadowDom(shadowRoot))
            serializedNode.isShadowHost = true;
    }
    if ((serializedNode.type === NodeType$1.Document ||
        serializedNode.type === NodeType$1.Element) &&
        recordChild) {
        if (slimDOMOptions.headWhitespace &&
            serializedNode.type === NodeType$1.Element &&
            serializedNode.tagName === 'head') {
            preserveWhiteSpace = false;
        }
        const bypassOptions = {
            doc,
            mirror,
            blockClass,
            blockSelector,
            maskAllText,
            unblockSelector,
            maskTextClass,
            unmaskTextClass,
            maskTextSelector,
            unmaskTextSelector,
            skipChild,
            inlineStylesheet,
            maskInputOptions,
            maskAttributeFn,
            maskTextFn,
            maskInputFn,
            slimDOMOptions,
            dataURLOptions,
            inlineImages,
            recordCanvas,
            preserveWhiteSpace,
            onSerialize,
            onIframeLoad,
            iframeLoadTimeout,
            onStylesheetLoad,
            stylesheetLoadTimeout,
            keepIframeSrcFn,
        };
        for (const childN of Array.from(n.childNodes)) {
            const serializedChildNode = serializeNodeWithId(childN, bypassOptions);
            if (serializedChildNode) {
                serializedNode.childNodes.push(serializedChildNode);
            }
        }
        if (isElement$1(n) && n.shadowRoot) {
            for (const childN of Array.from(n.shadowRoot.childNodes)) {
                const serializedChildNode = serializeNodeWithId(childN, bypassOptions);
                if (serializedChildNode) {
                    isNativeShadowDom(n.shadowRoot) &&
                        (serializedChildNode.isShadow = true);
                    serializedNode.childNodes.push(serializedChildNode);
                }
            }
        }
    }
    if (n.parentNode &&
        isShadowRoot(n.parentNode) &&
        isNativeShadowDom(n.parentNode)) {
        serializedNode.isShadow = true;
    }
    if (serializedNode.type === NodeType$1.Element &&
        serializedNode.tagName === 'iframe') {
        onceIframeLoaded(n, () => {
            const iframeDoc = n.contentDocument;
            if (iframeDoc && onIframeLoad) {
                const serializedIframeNode = serializeNodeWithId(iframeDoc, {
                    doc: iframeDoc,
                    mirror,
                    blockClass,
                    blockSelector,
                    unblockSelector,
                    maskAllText,
                    maskTextClass,
                    unmaskTextClass,
                    maskTextSelector,
                    unmaskTextSelector,
                    skipChild: false,
                    inlineStylesheet,
                    maskInputOptions,
                    maskAttributeFn,
                    maskTextFn,
                    maskInputFn,
                    slimDOMOptions,
                    dataURLOptions,
                    inlineImages,
                    recordCanvas,
                    preserveWhiteSpace,
                    onSerialize,
                    onIframeLoad,
                    iframeLoadTimeout,
                    onStylesheetLoad,
                    stylesheetLoadTimeout,
                    keepIframeSrcFn,
                });
                if (serializedIframeNode) {
                    onIframeLoad(n, serializedIframeNode);
                }
            }
        }, iframeLoadTimeout);
    }
    if (serializedNode.type === NodeType$1.Element &&
        serializedNode.tagName === 'link' &&
        serializedNode.attributes.rel === 'stylesheet') {
        onceStylesheetLoaded(n, () => {
            if (onStylesheetLoad) {
                const serializedLinkNode = serializeNodeWithId(n, {
                    doc,
                    mirror,
                    blockClass,
                    blockSelector,
                    unblockSelector,
                    maskAllText,
                    maskTextClass,
                    unmaskTextClass,
                    maskTextSelector,
                    unmaskTextSelector,
                    skipChild: false,
                    inlineStylesheet,
                    maskInputOptions,
                    maskAttributeFn,
                    maskTextFn,
                    maskInputFn,
                    slimDOMOptions,
                    dataURLOptions,
                    inlineImages,
                    recordCanvas,
                    preserveWhiteSpace,
                    onSerialize,
                    onIframeLoad,
                    iframeLoadTimeout,
                    onStylesheetLoad,
                    stylesheetLoadTimeout,
                    keepIframeSrcFn,
                });
                if (serializedLinkNode) {
                    onStylesheetLoad(n, serializedLinkNode);
                }
            }
        }, stylesheetLoadTimeout);
    }
    return serializedNode;
}
function snapshot(n, options) {
    const { mirror = new Mirror(), blockClass = 'rr-block', blockSelector = null, unblockSelector = null, maskAllText = false, maskTextClass = 'rr-mask', unmaskTextClass = null, maskTextSelector = null, unmaskTextSelector = null, inlineStylesheet = true, inlineImages = false, recordCanvas = false, maskAllInputs = false, maskAttributeFn, maskTextFn, maskInputFn, slimDOM = false, dataURLOptions, preserveWhiteSpace, onSerialize, onIframeLoad, iframeLoadTimeout, onStylesheetLoad, stylesheetLoadTimeout, keepIframeSrcFn = () => false, } = options || {};
    const maskInputOptions = maskAllInputs === true
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
        }
        : maskAllInputs === false
            ? {}
            : maskAllInputs;
    const slimDOMOptions = slimDOM === true || slimDOM === 'all'
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
                headMetaVerification: true,
            }
        : slimDOM === false
            ? {}
            : slimDOM;
    return serializeNodeWithId(n, {
        doc: n,
        mirror,
        blockClass,
        blockSelector,
        unblockSelector,
        maskAllText,
        maskTextClass,
        unmaskTextClass,
        maskTextSelector,
        unmaskTextSelector,
        skipChild: false,
        inlineStylesheet,
        maskInputOptions,
        maskAttributeFn,
        maskTextFn,
        maskInputFn,
        slimDOMOptions,
        dataURLOptions,
        inlineImages,
        recordCanvas,
        preserveWhiteSpace,
        onSerialize,
        onIframeLoad,
        iframeLoadTimeout,
        onStylesheetLoad,
        stylesheetLoadTimeout,
        keepIframeSrcFn,
        newlyAddedElement: false,
    });
}

function on(type, fn, target = document) {
    const options = { capture: true, passive: true };
    target.addEventListener(type, fn, options);
    return () => target.removeEventListener(type, fn, options);
}
const DEPARTED_MIRROR_ACCESS_WARNING = 'Please stop import mirror directly. Instead of that,' +
    '\r\n' +
    'now you can use replayer.getMirror() to access the mirror instance of a replayer,' +
    '\r\n' +
    'or you can use record.mirror to access the mirror instance during recording.';
let _mirror = {
    map: {},
    getId() {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
        return -1;
    },
    getNode() {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
        return null;
    },
    removeNodeFromMap() {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
    },
    has() {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
        return false;
    },
    reset() {
        console.error(DEPARTED_MIRROR_ACCESS_WARNING);
    },
};
if (typeof window !== 'undefined' && window.Proxy && window.Reflect) {
    _mirror = new Proxy(_mirror, {
        get(target, prop, receiver) {
            if (prop === 'map') {
                console.error(DEPARTED_MIRROR_ACCESS_WARNING);
            }
            return Reflect.get(target, prop, receiver);
        },
    });
}
function throttle$1(func, wait, options = {}) {
    let timeout = null;
    let previous = 0;
    return function (...args) {
        const now = Date.now();
        if (!previous && options.leading === false) {
            previous = now;
        }
        const remaining = wait - (now - previous);
        const context = this;
        if (remaining <= 0 || remaining > wait) {
            if (timeout) {
                clearTimeout(timeout);
                timeout = null;
            }
            previous = now;
            func.apply(context, args);
        }
        else if (!timeout && options.trailing !== false) {
            timeout = setTimeout(() => {
                previous = options.leading === false ? 0 : Date.now();
                timeout = null;
                func.apply(context, args);
            }, remaining);
        }
    };
}
function hookSetter(target, key, d, isRevoked, win = window) {
    const original = win.Object.getOwnPropertyDescriptor(target, key);
    win.Object.defineProperty(target, key, isRevoked
        ? d
        : {
            set(value) {
                setTimeout(() => {
                    d.set.call(this, value);
                }, 0);
                if (original && original.set) {
                    original.set.call(this, value);
                }
            },
        });
    return () => hookSetter(target, key, original || {}, true);
}
function patch(source, name, replacement) {
    try {
        if (!(name in source)) {
            return () => {
            };
        }
        const original = source[name];
        const wrapped = replacement(original);
        if (typeof wrapped === 'function') {
            wrapped.prototype = wrapped.prototype || {};
            Object.defineProperties(wrapped, {
                __rrweb_original__: {
                    enumerable: false,
                    value: original,
                },
            });
        }
        source[name] = wrapped;
        return () => {
            source[name] = original;
        };
    }
    catch (_a) {
        return () => {
        };
    }
}
let nowTimestamp = Date.now;
if (!(/[1-9][0-9]{12}/.test(Date.now().toString()))) {
    nowTimestamp = () => new Date().getTime();
}
function getWindowScroll(win) {
    var _a, _b, _c, _d, _e, _f;
    const doc = win.document;
    return {
        left: doc.scrollingElement
            ? doc.scrollingElement.scrollLeft
            : win.pageXOffset !== undefined
                ? win.pageXOffset
                : (doc === null || doc === void 0 ? void 0 : doc.documentElement.scrollLeft) ||
                    ((_b = (_a = doc === null || doc === void 0 ? void 0 : doc.body) === null || _a === void 0 ? void 0 : _a.parentElement) === null || _b === void 0 ? void 0 : _b.scrollLeft) ||
                    ((_c = doc === null || doc === void 0 ? void 0 : doc.body) === null || _c === void 0 ? void 0 : _c.scrollLeft) ||
                    0,
        top: doc.scrollingElement
            ? doc.scrollingElement.scrollTop
            : win.pageYOffset !== undefined
                ? win.pageYOffset
                : (doc === null || doc === void 0 ? void 0 : doc.documentElement.scrollTop) ||
                    ((_e = (_d = doc === null || doc === void 0 ? void 0 : doc.body) === null || _d === void 0 ? void 0 : _d.parentElement) === null || _e === void 0 ? void 0 : _e.scrollTop) ||
                    ((_f = doc === null || doc === void 0 ? void 0 : doc.body) === null || _f === void 0 ? void 0 : _f.scrollTop) ||
                    0,
    };
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
function isBlocked(node, blockClass, blockSelector, unblockSelector, checkAncestors) {
    if (!node) {
        return false;
    }
    const el = node.nodeType === node.ELEMENT_NODE
        ? node
        : node.parentElement;
    if (!el)
        return false;
    const blockedPredicate = createMatchPredicate(blockClass, blockSelector);
    if (!checkAncestors) {
        const isUnblocked = unblockSelector && el.matches(unblockSelector);
        return blockedPredicate(el) && !isUnblocked;
    }
    const blockDistance = distanceToMatch(el, blockedPredicate);
    let unblockDistance = -1;
    if (blockDistance < 0) {
        return false;
    }
    if (unblockSelector) {
        unblockDistance = distanceToMatch(el, createMatchPredicate(null, unblockSelector));
    }
    if (blockDistance > -1 && unblockDistance < 0) {
        return true;
    }
    return blockDistance < unblockDistance;
}
function isSerialized(n, mirror) {
    return mirror.getId(n) !== -1;
}
function isIgnored(n, mirror) {
    return mirror.getId(n) === IGNORED_NODE;
}
function isAncestorRemoved(target, mirror) {
    if (isShadowRoot(target)) {
        return false;
    }
    const id = mirror.getId(target);
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
function legacy_isTouchEvent(event) {
    return Boolean(event.changedTouches);
}
function polyfill(win = window) {
    if ('NodeList' in win && !win.NodeList.prototype.forEach) {
        win.NodeList.prototype.forEach = Array.prototype
            .forEach;
    }
    if ('DOMTokenList' in win && !win.DOMTokenList.prototype.forEach) {
        win.DOMTokenList.prototype.forEach = Array.prototype
            .forEach;
    }
    if (!Node.prototype.contains) {
        Node.prototype.contains = (...args) => {
            let node = args[0];
            if (!(0 in args)) {
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
function isSerializedIframe(n, mirror) {
    return Boolean(n.nodeName === 'IFRAME' && mirror.getMeta(n));
}
function isSerializedStylesheet(n, mirror) {
    return Boolean(n.nodeName === 'LINK' &&
        n.nodeType === n.ELEMENT_NODE &&
        n.getAttribute &&
        n.getAttribute('rel') === 'stylesheet' &&
        mirror.getMeta(n));
}
function hasShadowRoot(n) {
    return Boolean(n === null || n === void 0 ? void 0 : n.shadowRoot);
}
class StyleSheetMirror {
    constructor() {
        this.id = 1;
        this.styleIDMap = new WeakMap();
        this.idStyleMap = new Map();
    }
    getId(stylesheet) {
        var _a;
        return (_a = this.styleIDMap.get(stylesheet)) !== null && _a !== void 0 ? _a : -1;
    }
    has(stylesheet) {
        return this.styleIDMap.has(stylesheet);
    }
    add(stylesheet, id) {
        if (this.has(stylesheet))
            return this.getId(stylesheet);
        let newId;
        if (id === undefined) {
            newId = this.id++;
        }
        else
            newId = id;
        this.styleIDMap.set(stylesheet, newId);
        this.idStyleMap.set(newId, stylesheet);
        return newId;
    }
    getStyle(id) {
        return this.idStyleMap.get(id) || null;
    }
    reset() {
        this.styleIDMap = new WeakMap();
        this.idStyleMap = new Map();
        this.id = 1;
    }
    generateId() {
        return this.id++;
    }
}
function getShadowHost(n) {
    var _a, _b;
    let shadowHost = null;
    if (((_b = (_a = n.getRootNode) === null || _a === void 0 ? void 0 : _a.call(n)) === null || _b === void 0 ? void 0 : _b.nodeType) === Node.DOCUMENT_FRAGMENT_NODE &&
        n.getRootNode().host)
        shadowHost = n.getRootNode().host;
    return shadowHost;
}
function getRootShadowHost(n) {
    let rootShadowHost = n;
    let shadowHost;
    while ((shadowHost = getShadowHost(rootShadowHost)))
        rootShadowHost = shadowHost;
    return rootShadowHost;
}
function shadowHostInDom(n) {
    const doc = n.ownerDocument;
    if (!doc)
        return false;
    const shadowHost = getRootShadowHost(n);
    return doc.contains(shadowHost);
}
function inDom(n) {
    const doc = n.ownerDocument;
    if (!doc)
        return false;
    return doc.contains(n) || shadowHostInDom(n);
}

var EventType = /* @__PURE__ */ ((EventType2) => {
  EventType2[EventType2["DomContentLoaded"] = 0] = "DomContentLoaded";
  EventType2[EventType2["Load"] = 1] = "Load";
  EventType2[EventType2["FullSnapshot"] = 2] = "FullSnapshot";
  EventType2[EventType2["IncrementalSnapshot"] = 3] = "IncrementalSnapshot";
  EventType2[EventType2["Meta"] = 4] = "Meta";
  EventType2[EventType2["Custom"] = 5] = "Custom";
  EventType2[EventType2["Plugin"] = 6] = "Plugin";
  return EventType2;
})(EventType || {});
var IncrementalSource = /* @__PURE__ */ ((IncrementalSource2) => {
  IncrementalSource2[IncrementalSource2["Mutation"] = 0] = "Mutation";
  IncrementalSource2[IncrementalSource2["MouseMove"] = 1] = "MouseMove";
  IncrementalSource2[IncrementalSource2["MouseInteraction"] = 2] = "MouseInteraction";
  IncrementalSource2[IncrementalSource2["Scroll"] = 3] = "Scroll";
  IncrementalSource2[IncrementalSource2["ViewportResize"] = 4] = "ViewportResize";
  IncrementalSource2[IncrementalSource2["Input"] = 5] = "Input";
  IncrementalSource2[IncrementalSource2["TouchMove"] = 6] = "TouchMove";
  IncrementalSource2[IncrementalSource2["MediaInteraction"] = 7] = "MediaInteraction";
  IncrementalSource2[IncrementalSource2["StyleSheetRule"] = 8] = "StyleSheetRule";
  IncrementalSource2[IncrementalSource2["CanvasMutation"] = 9] = "CanvasMutation";
  IncrementalSource2[IncrementalSource2["Font"] = 10] = "Font";
  IncrementalSource2[IncrementalSource2["Log"] = 11] = "Log";
  IncrementalSource2[IncrementalSource2["Drag"] = 12] = "Drag";
  IncrementalSource2[IncrementalSource2["StyleDeclaration"] = 13] = "StyleDeclaration";
  IncrementalSource2[IncrementalSource2["Selection"] = 14] = "Selection";
  IncrementalSource2[IncrementalSource2["AdoptedStyleSheet"] = 15] = "AdoptedStyleSheet";
  IncrementalSource2[IncrementalSource2["CustomElement"] = 16] = "CustomElement";
  return IncrementalSource2;
})(IncrementalSource || {});
var MouseInteractions = /* @__PURE__ */ ((MouseInteractions2) => {
  MouseInteractions2[MouseInteractions2["MouseUp"] = 0] = "MouseUp";
  MouseInteractions2[MouseInteractions2["MouseDown"] = 1] = "MouseDown";
  MouseInteractions2[MouseInteractions2["Click"] = 2] = "Click";
  MouseInteractions2[MouseInteractions2["ContextMenu"] = 3] = "ContextMenu";
  MouseInteractions2[MouseInteractions2["DblClick"] = 4] = "DblClick";
  MouseInteractions2[MouseInteractions2["Focus"] = 5] = "Focus";
  MouseInteractions2[MouseInteractions2["Blur"] = 6] = "Blur";
  MouseInteractions2[MouseInteractions2["TouchStart"] = 7] = "TouchStart";
  MouseInteractions2[MouseInteractions2["TouchMove_Departed"] = 8] = "TouchMove_Departed";
  MouseInteractions2[MouseInteractions2["TouchEnd"] = 9] = "TouchEnd";
  MouseInteractions2[MouseInteractions2["TouchCancel"] = 10] = "TouchCancel";
  return MouseInteractions2;
})(MouseInteractions || {});
var PointerTypes = /* @__PURE__ */ ((PointerTypes2) => {
  PointerTypes2[PointerTypes2["Mouse"] = 0] = "Mouse";
  PointerTypes2[PointerTypes2["Pen"] = 1] = "Pen";
  PointerTypes2[PointerTypes2["Touch"] = 2] = "Touch";
  return PointerTypes2;
})(PointerTypes || {});

function isNodeInLinkedList(n) {
    return '__ln' in n;
}
class DoubleLinkedList {
    constructor() {
        this.length = 0;
        this.head = null;
        this.tail = null;
    }
    get(position) {
        if (position >= this.length) {
            throw new Error('Position outside of list range');
        }
        let current = this.head;
        for (let index = 0; index < position; index++) {
            current = (current === null || current === void 0 ? void 0 : current.next) || null;
        }
        return current;
    }
    addNode(n) {
        const node = {
            value: n,
            previous: null,
            next: null,
        };
        n.__ln = node;
        if (n.previousSibling && isNodeInLinkedList(n.previousSibling)) {
            const current = n.previousSibling.__ln.next;
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
            const current = n.nextSibling.__ln.previous;
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
        if (node.next === null) {
            this.tail = node;
        }
        this.length++;
    }
    removeNode(n) {
        const current = n.__ln;
        if (!this.head) {
            return;
        }
        if (!current.previous) {
            this.head = current.next;
            if (this.head) {
                this.head.previous = null;
            }
            else {
                this.tail = null;
            }
        }
        else {
            current.previous.next = current.next;
            if (current.next) {
                current.next.previous = current.previous;
            }
            else {
                this.tail = current.previous;
            }
        }
        if (n.__ln) {
            delete n.__ln;
        }
        this.length--;
    }
}
const moveKey = (id, parentId) => `${id}@${parentId}`;
class MutationBuffer {
    constructor() {
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
        this.processMutations = (mutations) => {
            mutations.forEach(this.processMutation);
            this.emit();
        };
        this.emit = () => {
            if (this.frozen || this.locked) {
                return;
            }
            const adds = [];
            const addedIds = new Set();
            const addList = new DoubleLinkedList();
            const getNextId = (n) => {
                let ns = n;
                let nextId = IGNORED_NODE;
                while (nextId === IGNORED_NODE) {
                    ns = ns && ns.nextSibling;
                    nextId = ns && this.mirror.getId(ns);
                }
                return nextId;
            };
            const pushAdd = (n) => {
                if (!n.parentNode || !inDom(n)) {
                    return;
                }
                const parentId = isShadowRoot(n.parentNode)
                    ? this.mirror.getId(getShadowHost(n))
                    : this.mirror.getId(n.parentNode);
                const nextId = getNextId(n);
                if (parentId === -1 || nextId === -1) {
                    return addList.addNode(n);
                }
                const sn = serializeNodeWithId(n, {
                    doc: this.doc,
                    mirror: this.mirror,
                    blockClass: this.blockClass,
                    blockSelector: this.blockSelector,
                    maskAllText: this.maskAllText,
                    unblockSelector: this.unblockSelector,
                    maskTextClass: this.maskTextClass,
                    unmaskTextClass: this.unmaskTextClass,
                    maskTextSelector: this.maskTextSelector,
                    unmaskTextSelector: this.unmaskTextSelector,
                    skipChild: true,
                    newlyAddedElement: true,
                    inlineStylesheet: this.inlineStylesheet,
                    maskInputOptions: this.maskInputOptions,
                    maskAttributeFn: this.maskAttributeFn,
                    maskTextFn: this.maskTextFn,
                    maskInputFn: this.maskInputFn,
                    slimDOMOptions: this.slimDOMOptions,
                    dataURLOptions: this.dataURLOptions,
                    recordCanvas: this.recordCanvas,
                    inlineImages: this.inlineImages,
                    onSerialize: (currentN) => {
                        if (isSerializedIframe(currentN, this.mirror)) {
                            this.iframeManager.addIframe(currentN);
                        }
                        if (isSerializedStylesheet(currentN, this.mirror)) {
                            this.stylesheetManager.trackLinkElement(currentN);
                        }
                        if (hasShadowRoot(n)) {
                            this.shadowDomManager.addShadowRoot(n.shadowRoot, this.doc);
                        }
                    },
                    onIframeLoad: (iframe, childSn) => {
                        this.iframeManager.attachIframe(iframe, childSn);
                        this.shadowDomManager.observeAttachShadow(iframe);
                    },
                    onStylesheetLoad: (link, childSn) => {
                        this.stylesheetManager.attachLinkElement(link, childSn);
                    },
                });
                if (sn) {
                    adds.push({
                        parentId,
                        nextId,
                        node: sn,
                    });
                    addedIds.add(sn.id);
                }
            };
            while (this.mapRemoves.length) {
                this.mirror.removeNodeFromMap(this.mapRemoves.shift());
            }
            for (const n of this.movedSet) {
                if (isParentRemoved(this.removes, n, this.mirror) &&
                    !this.movedSet.has(n.parentNode)) {
                    continue;
                }
                pushAdd(n);
            }
            for (const n of this.addedSet) {
                if (!isAncestorInSet(this.droppedSet, n) &&
                    !isParentRemoved(this.removes, n, this.mirror)) {
                    pushAdd(n);
                }
                else if (isAncestorInSet(this.movedSet, n)) {
                    pushAdd(n);
                }
                else {
                    this.droppedSet.add(n);
                }
            }
            let candidate = null;
            while (addList.length) {
                let node = null;
                if (candidate) {
                    const parentId = this.mirror.getId(candidate.value.parentNode);
                    const nextId = getNextId(candidate.value);
                    if (parentId !== -1 && nextId !== -1) {
                        node = candidate;
                    }
                }
                if (!node) {
                    let tailNode = addList.tail;
                    while (tailNode) {
                        const _node = tailNode;
                        tailNode = tailNode.previous;
                        if (_node) {
                            const parentId = this.mirror.getId(_node.value.parentNode);
                            const nextId = getNextId(_node.value);
                            if (nextId === -1)
                                continue;
                            else if (parentId !== -1) {
                                node = _node;
                                break;
                            }
                            else {
                                const unhandledNode = _node.value;
                                if (unhandledNode.parentNode &&
                                    unhandledNode.parentNode.nodeType ===
                                        Node.DOCUMENT_FRAGMENT_NODE) {
                                    const shadowHost = unhandledNode.parentNode
                                        .host;
                                    const parentId = this.mirror.getId(shadowHost);
                                    if (parentId !== -1) {
                                        node = _node;
                                        break;
                                    }
                                }
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
            const payload = {
                texts: this.texts
                    .map((text) => ({
                    id: this.mirror.getId(text.node),
                    value: text.value,
                }))
                    .filter((text) => !addedIds.has(text.id))
                    .filter((text) => this.mirror.has(text.id)),
                attributes: this.attributes
                    .map((attribute) => {
                    const { attributes } = attribute;
                    if (typeof attributes.style === 'string') {
                        const diffAsStr = JSON.stringify(attribute.styleDiff);
                        const unchangedAsStr = JSON.stringify(attribute._unchangedStyles);
                        if (diffAsStr.length < attributes.style.length) {
                            if ((diffAsStr + unchangedAsStr).split('var(').length ===
                                attributes.style.split('var(').length) {
                                attributes.style = attribute.styleDiff;
                            }
                        }
                    }
                    return {
                        id: this.mirror.getId(attribute.node),
                        attributes: attributes,
                    };
                })
                    .filter((attribute) => !addedIds.has(attribute.id))
                    .filter((attribute) => this.mirror.has(attribute.id)),
                removes: this.removes,
                adds,
            };
            if (!payload.texts.length &&
                !payload.attributes.length &&
                !payload.removes.length &&
                !payload.adds.length) {
                return;
            }
            this.texts = [];
            this.attributes = [];
            this.removes = [];
            this.addedSet = new Set();
            this.movedSet = new Set();
            this.droppedSet = new Set();
            this.movedMap = {};
            this.mutationCb(payload);
        };
        this.processMutation = (m) => {
            if (isIgnored(m.target, this.mirror)) {
                return;
            }
            let unattachedDoc;
            try {
                unattachedDoc = document.implementation.createHTMLDocument();
            }
            catch (e) {
                unattachedDoc = this.doc;
            }
            switch (m.type) {
                case 'characterData': {
                    const value = m.target.textContent;
                    if (!isBlocked(m.target, this.blockClass, this.blockSelector, this.unblockSelector, false) &&
                        value !== m.oldValue) {
                        this.texts.push({
                            value: needMaskingText(m.target, this.maskTextClass, this.maskTextSelector, this.unmaskTextClass, this.unmaskTextSelector, this.maskAllText) && value
                                ? this.maskTextFn
                                    ? this.maskTextFn(value)
                                    : value.replace(/[\S]/g, '*')
                                : value,
                            node: m.target,
                        });
                    }
                    break;
                }
                case 'attributes': {
                    const target = m.target;
                    let attributeName = m.attributeName;
                    let value = m.target.getAttribute(attributeName);
                    if (attributeName === 'value') {
                        const type = getInputType(target);
                        const tagName = target.tagName;
                        value = getInputValue(target, tagName, type);
                        const isInputMasked = shouldMaskInput({
                            maskInputOptions: this.maskInputOptions,
                            tagName,
                            type,
                        });
                        const forceMask = needMaskingText(m.target, this.maskTextClass, this.maskTextSelector, this.unmaskTextClass, this.unmaskTextSelector, isInputMasked);
                        value = maskInputValue({
                            isMasked: forceMask,
                            element: target,
                            value,
                            maskInputFn: this.maskInputFn,
                        });
                    }
                    if (isBlocked(m.target, this.blockClass, this.blockSelector, this.unblockSelector, false) ||
                        value === m.oldValue) {
                        return;
                    }
                    let item = this.attributes.find((a) => a.node === m.target);
                    if (target.tagName === 'IFRAME' &&
                        attributeName === 'src' &&
                        !this.keepIframeSrcFn(value)) {
                        if (!target.contentDocument) {
                            attributeName = 'rr_src';
                        }
                        else {
                            return;
                        }
                    }
                    if (!item) {
                        item = {
                            node: m.target,
                            attributes: {},
                            styleDiff: {},
                            _unchangedStyles: {},
                        };
                        this.attributes.push(item);
                    }
                    if (attributeName === 'type' &&
                        target.tagName === 'INPUT' &&
                        (m.oldValue || '').toLowerCase() === 'password') {
                        target.setAttribute('data-rr-is-password', 'true');
                    }
                    if (!ignoreAttribute(target.tagName, attributeName)) {
                        item.attributes[attributeName] = transformAttribute(this.doc, toLowerCase(target.tagName), toLowerCase(attributeName), value, target, this.maskAttributeFn);
                        if (attributeName === 'style') {
                            const old = unattachedDoc.createElement('span');
                            if (m.oldValue) {
                                old.setAttribute('style', m.oldValue);
                            }
                            for (const pname of Array.from(target.style)) {
                                const newValue = target.style.getPropertyValue(pname);
                                const newPriority = target.style.getPropertyPriority(pname);
                                if (newValue !== old.style.getPropertyValue(pname) ||
                                    newPriority !== old.style.getPropertyPriority(pname)) {
                                    if (newPriority === '') {
                                        item.styleDiff[pname] = newValue;
                                    }
                                    else {
                                        item.styleDiff[pname] = [newValue, newPriority];
                                    }
                                }
                                else {
                                    item._unchangedStyles[pname] = [newValue, newPriority];
                                }
                            }
                            for (const pname of Array.from(old.style)) {
                                if (target.style.getPropertyValue(pname) === '') {
                                    item.styleDiff[pname] = false;
                                }
                            }
                        }
                    }
                    break;
                }
                case 'childList': {
                    if (isBlocked(m.target, this.blockClass, this.blockSelector, this.unblockSelector, true)) {
                        return;
                    }
                    m.addedNodes.forEach((n) => this.genAdds(n, m.target));
                    m.removedNodes.forEach((n) => {
                        const nodeId = this.mirror.getId(n);
                        const parentId = isShadowRoot(m.target)
                            ? this.mirror.getId(m.target.host)
                            : this.mirror.getId(m.target);
                        if (isBlocked(m.target, this.blockClass, this.blockSelector, this.unblockSelector, false) ||
                            isIgnored(n, this.mirror) ||
                            !isSerialized(n, this.mirror)) {
                            return;
                        }
                        if (this.addedSet.has(n)) {
                            deepDelete(this.addedSet, n);
                            this.droppedSet.add(n);
                        }
                        else if (this.addedSet.has(m.target) && nodeId === -1) ;
                        else if (isAncestorRemoved(m.target, this.mirror)) ;
                        else if (this.movedSet.has(n) &&
                            this.movedMap[moveKey(nodeId, parentId)]) {
                            deepDelete(this.movedSet, n);
                        }
                        else {
                            this.removes.push({
                                parentId,
                                id: nodeId,
                                isShadow: isShadowRoot(m.target) && isNativeShadowDom(m.target)
                                    ? true
                                    : undefined,
                            });
                        }
                        this.mapRemoves.push(n);
                    });
                    break;
                }
            }
        };
        this.genAdds = (n, target) => {
            if (this.processedNodeManager.inOtherBuffer(n, this))
                return;
            if (this.addedSet.has(n) || this.movedSet.has(n))
                return;
            if (this.mirror.hasNode(n)) {
                if (isIgnored(n, this.mirror)) {
                    return;
                }
                this.movedSet.add(n);
                let targetId = null;
                if (target && this.mirror.hasNode(target)) {
                    targetId = this.mirror.getId(target);
                }
                if (targetId && targetId !== -1) {
                    this.movedMap[moveKey(this.mirror.getId(n), targetId)] = true;
                }
            }
            else {
                this.addedSet.add(n);
                this.droppedSet.delete(n);
            }
            if (!isBlocked(n, this.blockClass, this.blockSelector, this.unblockSelector, false)) {
                n.childNodes.forEach((childN) => this.genAdds(childN));
                if (hasShadowRoot(n)) {
                    n.shadowRoot.childNodes.forEach((childN) => {
                        this.processedNodeManager.add(childN, this);
                        this.genAdds(childN, n);
                    });
                }
            }
        };
    }
    init(options) {
        [
            'mutationCb',
            'blockClass',
            'blockSelector',
            'unblockSelector',
            'maskAllText',
            'maskTextClass',
            'unmaskTextClass',
            'maskTextSelector',
            'unmaskTextSelector',
            'inlineStylesheet',
            'maskInputOptions',
            'maskAttributeFn',
            'maskTextFn',
            'maskInputFn',
            'keepIframeSrcFn',
            'recordCanvas',
            'inlineImages',
            'slimDOMOptions',
            'dataURLOptions',
            'doc',
            'mirror',
            'iframeManager',
            'stylesheetManager',
            'shadowDomManager',
            'canvasManager',
            'processedNodeManager',
        ].forEach((key) => {
            this[key] = options[key];
        });
    }
    freeze() {
        this.frozen = true;
        this.canvasManager.freeze();
    }
    unfreeze() {
        this.frozen = false;
        this.canvasManager.unfreeze();
        this.emit();
    }
    isFrozen() {
        return this.frozen;
    }
    lock() {
        this.locked = true;
        this.canvasManager.lock();
    }
    unlock() {
        this.locked = false;
        this.canvasManager.unlock();
        this.emit();
    }
    reset() {
        this.shadowDomManager.reset();
        this.canvasManager.reset();
    }
}
function deepDelete(addsSet, n) {
    addsSet.delete(n);
    n.childNodes.forEach((childN) => deepDelete(addsSet, childN));
}
function isParentRemoved(removes, n, mirror) {
    if (removes.length === 0)
        return false;
    return _isParentRemoved(removes, n, mirror);
}
function _isParentRemoved(removes, n, mirror) {
    const { parentNode } = n;
    if (!parentNode) {
        return false;
    }
    const parentId = mirror.getId(parentNode);
    if (removes.some((r) => r.id === parentId)) {
        return true;
    }
    return _isParentRemoved(removes, parentNode, mirror);
}
function isAncestorInSet(set, n) {
    if (set.size === 0)
        return false;
    return _isAncestorInSet(set, n);
}
function _isAncestorInSet(set, n) {
    const { parentNode } = n;
    if (!parentNode) {
        return false;
    }
    if (set.has(parentNode)) {
        return true;
    }
    return _isAncestorInSet(set, parentNode);
}

let errorHandler;
function registerErrorHandler(handler) {
    errorHandler = handler;
}
function unregisterErrorHandler() {
    errorHandler = undefined;
}
const callbackWrapper = (cb) => {
    if (!errorHandler) {
        return cb;
    }
    const rrwebWrapped = ((...rest) => {
        try {
            return cb(...rest);
        }
        catch (error) {
            if (errorHandler && errorHandler(error) === true) {
                return () => {
                };
            }
            throw error;
        }
    });
    return rrwebWrapped;
};

const mutationBuffers = [];
function getEventTarget(event) {
    try {
        if ('composedPath' in event) {
            const path = event.composedPath();
            if (path.length) {
                return path[0];
            }
        }
        else if ('path' in event && event.path.length) {
            return event.path[0];
        }
    }
    catch (_a) {
    }
    return event && event.target;
}
function initMutationObserver(options, rootEl) {
    var _a, _b;
    const mutationBuffer = new MutationBuffer();
    mutationBuffers.push(mutationBuffer);
    mutationBuffer.init(options);
    let mutationObserverCtor = window.MutationObserver ||
        window.__rrMutationObserver;
    const angularZoneSymbol = (_b = (_a = window === null || window === void 0 ? void 0 : window.Zone) === null || _a === void 0 ? void 0 : _a.__symbol__) === null || _b === void 0 ? void 0 : _b.call(_a, 'MutationObserver');
    if (angularZoneSymbol &&
        window[angularZoneSymbol]) {
        mutationObserverCtor = window[angularZoneSymbol];
    }
    const observer = new mutationObserverCtor(callbackWrapper((mutations) => {
        if (options.onMutation && options.onMutation(mutations) === false) {
            return;
        }
        mutationBuffer.processMutations.bind(mutationBuffer)(mutations);
    }));
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
function initMoveObserver({ mousemoveCb, sampling, doc, mirror, }) {
    if (sampling.mousemove === false) {
        return () => {
        };
    }
    const threshold = typeof sampling.mousemove === 'number' ? sampling.mousemove : 50;
    const callbackThreshold = typeof sampling.mousemoveCallback === 'number'
        ? sampling.mousemoveCallback
        : 500;
    let positions = [];
    let timeBaseline;
    const wrappedCb = throttle$1(callbackWrapper((source) => {
        const totalOffset = Date.now() - timeBaseline;
        mousemoveCb(positions.map((p) => {
            p.timeOffset -= totalOffset;
            return p;
        }), source);
        positions = [];
        timeBaseline = null;
    }), callbackThreshold);
    const updatePosition = callbackWrapper(throttle$1(callbackWrapper((evt) => {
        const target = getEventTarget(evt);
        const { clientX, clientY } = legacy_isTouchEvent(evt)
            ? evt.changedTouches[0]
            : evt;
        if (!timeBaseline) {
            timeBaseline = nowTimestamp();
        }
        positions.push({
            x: clientX,
            y: clientY,
            id: mirror.getId(target),
            timeOffset: nowTimestamp() - timeBaseline,
        });
        wrappedCb(typeof DragEvent !== 'undefined' && evt instanceof DragEvent
            ? IncrementalSource.Drag
            : evt instanceof MouseEvent
                ? IncrementalSource.MouseMove
                : IncrementalSource.TouchMove);
    }), threshold, {
        trailing: false,
    }));
    const handlers = [
        on('mousemove', updatePosition, doc),
        on('touchmove', updatePosition, doc),
        on('drag', updatePosition, doc),
    ];
    return callbackWrapper(() => {
        handlers.forEach((h) => h());
    });
}
function initMouseInteractionObserver({ mouseInteractionCb, doc, mirror, blockClass, blockSelector, unblockSelector, sampling, }) {
    if (sampling.mouseInteraction === false) {
        return () => {
        };
    }
    const disableMap = sampling.mouseInteraction === true ||
        sampling.mouseInteraction === undefined
        ? {}
        : sampling.mouseInteraction;
    const handlers = [];
    let currentPointerType = null;
    const getHandler = (eventKey) => {
        return (event) => {
            const target = getEventTarget(event);
            if (isBlocked(target, blockClass, blockSelector, unblockSelector, true)) {
                return;
            }
            let pointerType = null;
            let thisEventKey = eventKey;
            if ('pointerType' in event) {
                switch (event.pointerType) {
                    case 'mouse':
                        pointerType = PointerTypes.Mouse;
                        break;
                    case 'touch':
                        pointerType = PointerTypes.Touch;
                        break;
                    case 'pen':
                        pointerType = PointerTypes.Pen;
                        break;
                }
                if (pointerType === PointerTypes.Touch) {
                    if (MouseInteractions[eventKey] === MouseInteractions.MouseDown) {
                        thisEventKey = 'TouchStart';
                    }
                    else if (MouseInteractions[eventKey] === MouseInteractions.MouseUp) {
                        thisEventKey = 'TouchEnd';
                    }
                }
                else if (pointerType === PointerTypes.Pen) ;
            }
            else if (legacy_isTouchEvent(event)) {
                pointerType = PointerTypes.Touch;
            }
            if (pointerType !== null) {
                currentPointerType = pointerType;
                if ((thisEventKey.startsWith('Touch') &&
                    pointerType === PointerTypes.Touch) ||
                    (thisEventKey.startsWith('Mouse') &&
                        pointerType === PointerTypes.Mouse)) {
                    pointerType = null;
                }
            }
            else if (MouseInteractions[eventKey] === MouseInteractions.Click) {
                pointerType = currentPointerType;
                currentPointerType = null;
            }
            const e = legacy_isTouchEvent(event) ? event.changedTouches[0] : event;
            if (!e) {
                return;
            }
            const id = mirror.getId(target);
            const { clientX, clientY } = e;
            callbackWrapper(mouseInteractionCb)(Object.assign({ type: MouseInteractions[thisEventKey], id, x: clientX, y: clientY }, (pointerType !== null && { pointerType })));
        };
    };
    Object.keys(MouseInteractions)
        .filter((key) => Number.isNaN(Number(key)) &&
        !key.endsWith('_Departed') &&
        disableMap[key] !== false)
        .forEach((eventKey) => {
        let eventName = toLowerCase(eventKey);
        const handler = getHandler(eventKey);
        if (window.PointerEvent) {
            switch (MouseInteractions[eventKey]) {
                case MouseInteractions.MouseDown:
                case MouseInteractions.MouseUp:
                    eventName = eventName.replace('mouse', 'pointer');
                    break;
                case MouseInteractions.TouchStart:
                case MouseInteractions.TouchEnd:
                    return;
            }
        }
        handlers.push(on(eventName, handler, doc));
    });
    return callbackWrapper(() => {
        handlers.forEach((h) => h());
    });
}
function initScrollObserver({ scrollCb, doc, mirror, blockClass, blockSelector, unblockSelector, sampling, }) {
    const updatePosition = callbackWrapper(throttle$1(callbackWrapper((evt) => {
        const target = getEventTarget(evt);
        if (!target ||
            isBlocked(target, blockClass, blockSelector, unblockSelector, true)) {
            return;
        }
        const id = mirror.getId(target);
        if (target === doc && doc.defaultView) {
            const scrollLeftTop = getWindowScroll(doc.defaultView);
            scrollCb({
                id,
                x: scrollLeftTop.left,
                y: scrollLeftTop.top,
            });
        }
        else {
            scrollCb({
                id,
                x: target.scrollLeft,
                y: target.scrollTop,
            });
        }
    }), sampling.scroll || 100));
    return on('scroll', updatePosition, doc);
}
function initViewportResizeObserver({ viewportResizeCb }, { win }) {
    let lastH = -1;
    let lastW = -1;
    const updateDimension = callbackWrapper(throttle$1(callbackWrapper(() => {
        const height = getWindowHeight();
        const width = getWindowWidth();
        if (lastH !== height || lastW !== width) {
            viewportResizeCb({
                width: Number(width),
                height: Number(height),
            });
            lastH = height;
            lastW = width;
        }
    }), 200));
    return on('resize', updateDimension, win);
}
const INPUT_TAGS = ['INPUT', 'TEXTAREA', 'SELECT'];
const lastInputValueMap = new WeakMap();
function initInputObserver({ inputCb, doc, mirror, blockClass, blockSelector, unblockSelector, ignoreClass, ignoreSelector, maskInputOptions, maskInputFn, sampling, userTriggeredOnInput, maskTextClass, unmaskTextClass, maskTextSelector, unmaskTextSelector, }) {
    function eventHandler(event) {
        let target = getEventTarget(event);
        const userTriggered = event.isTrusted;
        const tagName = target && toUpperCase(target.tagName);
        if (tagName === 'OPTION')
            target = target.parentElement;
        if (!target ||
            !tagName ||
            INPUT_TAGS.indexOf(tagName) < 0 ||
            isBlocked(target, blockClass, blockSelector, unblockSelector, true)) {
            return;
        }
        const el = target;
        if (el.classList.contains(ignoreClass) ||
            (ignoreSelector && el.matches(ignoreSelector))) {
            return;
        }
        const type = getInputType(target);
        let text = getInputValue(el, tagName, type);
        let isChecked = false;
        const isInputMasked = shouldMaskInput({
            maskInputOptions,
            tagName,
            type,
        });
        const forceMask = needMaskingText(target, maskTextClass, maskTextSelector, unmaskTextClass, unmaskTextSelector, isInputMasked);
        if (type === 'radio' || type === 'checkbox') {
            isChecked = target.checked;
        }
        text = maskInputValue({
            isMasked: forceMask,
            element: target,
            value: text,
            maskInputFn,
        });
        cbWithDedup(target, userTriggeredOnInput
            ? { text, isChecked, userTriggered }
            : { text, isChecked });
        const name = target.name;
        if (type === 'radio' && name && isChecked) {
            doc
                .querySelectorAll(`input[type="radio"][name="${name}"]`)
                .forEach((el) => {
                if (el !== target) {
                    const text = maskInputValue({
                        isMasked: forceMask,
                        element: el,
                        value: getInputValue(el, tagName, type),
                        maskInputFn,
                    });
                    cbWithDedup(el, userTriggeredOnInput
                        ? { text, isChecked: !isChecked, userTriggered: false }
                        : { text, isChecked: !isChecked });
                }
            });
        }
    }
    function cbWithDedup(target, v) {
        const lastInputValue = lastInputValueMap.get(target);
        if (!lastInputValue ||
            lastInputValue.text !== v.text ||
            lastInputValue.isChecked !== v.isChecked) {
            lastInputValueMap.set(target, v);
            const id = mirror.getId(target);
            callbackWrapper(inputCb)(Object.assign(Object.assign({}, v), { id }));
        }
    }
    const events = sampling.input === 'last' ? ['change'] : ['input', 'change'];
    const handlers = events.map((eventName) => on(eventName, callbackWrapper(eventHandler), doc));
    const currentWindow = doc.defaultView;
    if (!currentWindow) {
        return () => {
            handlers.forEach((h) => h());
        };
    }
    const propertyDescriptor = currentWindow.Object.getOwnPropertyDescriptor(currentWindow.HTMLInputElement.prototype, 'value');
    const hookProperties = [
        [currentWindow.HTMLInputElement.prototype, 'value'],
        [currentWindow.HTMLInputElement.prototype, 'checked'],
        [currentWindow.HTMLSelectElement.prototype, 'value'],
        [currentWindow.HTMLTextAreaElement.prototype, 'value'],
        [currentWindow.HTMLSelectElement.prototype, 'selectedIndex'],
        [currentWindow.HTMLOptionElement.prototype, 'selected'],
    ];
    if (propertyDescriptor && propertyDescriptor.set) {
        handlers.push(...hookProperties.map((p) => hookSetter(p[0], p[1], {
            set() {
                callbackWrapper(eventHandler)({
                    target: this,
                    isTrusted: false,
                });
            },
        }, false, currentWindow)));
    }
    return callbackWrapper(() => {
        handlers.forEach((h) => h());
    });
}
function getNestedCSSRulePositions(rule) {
    const positions = [];
    function recurse(childRule, pos) {
        if ((hasNestedCSSRule('CSSGroupingRule') &&
            childRule.parentRule instanceof CSSGroupingRule) ||
            (hasNestedCSSRule('CSSMediaRule') &&
                childRule.parentRule instanceof CSSMediaRule) ||
            (hasNestedCSSRule('CSSSupportsRule') &&
                childRule.parentRule instanceof CSSSupportsRule) ||
            (hasNestedCSSRule('CSSConditionRule') &&
                childRule.parentRule instanceof CSSConditionRule)) {
            const rules = Array.from(childRule.parentRule.cssRules);
            const index = rules.indexOf(childRule);
            pos.unshift(index);
        }
        else if (childRule.parentStyleSheet) {
            const rules = Array.from(childRule.parentStyleSheet.cssRules);
            const index = rules.indexOf(childRule);
            pos.unshift(index);
        }
        return pos;
    }
    return recurse(rule, positions);
}
function getIdAndStyleId(sheet, mirror, styleMirror) {
    let id, styleId;
    if (!sheet)
        return {};
    if (sheet.ownerNode)
        id = mirror.getId(sheet.ownerNode);
    else
        styleId = styleMirror.getId(sheet);
    return {
        styleId,
        id,
    };
}
function initStyleSheetObserver({ styleSheetRuleCb, mirror, stylesheetManager }, { win }) {
    if (!win.CSSStyleSheet || !win.CSSStyleSheet.prototype) {
        return () => {
        };
    }
    const insertRule = win.CSSStyleSheet.prototype.insertRule;
    win.CSSStyleSheet.prototype.insertRule = new Proxy(insertRule, {
        apply: callbackWrapper((target, thisArg, argumentsList) => {
            const [rule, index] = argumentsList;
            const { id, styleId } = getIdAndStyleId(thisArg, mirror, stylesheetManager.styleMirror);
            if ((id && id !== -1) || (styleId && styleId !== -1)) {
                styleSheetRuleCb({
                    id,
                    styleId,
                    adds: [{ rule, index }],
                });
            }
            return target.apply(thisArg, argumentsList);
        }),
    });
    const deleteRule = win.CSSStyleSheet.prototype.deleteRule;
    win.CSSStyleSheet.prototype.deleteRule = new Proxy(deleteRule, {
        apply: callbackWrapper((target, thisArg, argumentsList) => {
            const [index] = argumentsList;
            const { id, styleId } = getIdAndStyleId(thisArg, mirror, stylesheetManager.styleMirror);
            if ((id && id !== -1) || (styleId && styleId !== -1)) {
                styleSheetRuleCb({
                    id,
                    styleId,
                    removes: [{ index }],
                });
            }
            return target.apply(thisArg, argumentsList);
        }),
    });
    let replace;
    if (win.CSSStyleSheet.prototype.replace) {
        replace = win.CSSStyleSheet.prototype.replace;
        win.CSSStyleSheet.prototype.replace = new Proxy(replace, {
            apply: callbackWrapper((target, thisArg, argumentsList) => {
                const [text] = argumentsList;
                const { id, styleId } = getIdAndStyleId(thisArg, mirror, stylesheetManager.styleMirror);
                if ((id && id !== -1) || (styleId && styleId !== -1)) {
                    styleSheetRuleCb({
                        id,
                        styleId,
                        replace: text,
                    });
                }
                return target.apply(thisArg, argumentsList);
            }),
        });
    }
    let replaceSync;
    if (win.CSSStyleSheet.prototype.replaceSync) {
        replaceSync = win.CSSStyleSheet.prototype.replaceSync;
        win.CSSStyleSheet.prototype.replaceSync = new Proxy(replaceSync, {
            apply: callbackWrapper((target, thisArg, argumentsList) => {
                const [text] = argumentsList;
                const { id, styleId } = getIdAndStyleId(thisArg, mirror, stylesheetManager.styleMirror);
                if ((id && id !== -1) || (styleId && styleId !== -1)) {
                    styleSheetRuleCb({
                        id,
                        styleId,
                        replaceSync: text,
                    });
                }
                return target.apply(thisArg, argumentsList);
            }),
        });
    }
    const supportedNestedCSSRuleTypes = {};
    if (canMonkeyPatchNestedCSSRule('CSSGroupingRule')) {
        supportedNestedCSSRuleTypes.CSSGroupingRule = win.CSSGroupingRule;
    }
    else {
        if (canMonkeyPatchNestedCSSRule('CSSMediaRule')) {
            supportedNestedCSSRuleTypes.CSSMediaRule = win.CSSMediaRule;
        }
        if (canMonkeyPatchNestedCSSRule('CSSConditionRule')) {
            supportedNestedCSSRuleTypes.CSSConditionRule = win.CSSConditionRule;
        }
        if (canMonkeyPatchNestedCSSRule('CSSSupportsRule')) {
            supportedNestedCSSRuleTypes.CSSSupportsRule = win.CSSSupportsRule;
        }
    }
    const unmodifiedFunctions = {};
    Object.entries(supportedNestedCSSRuleTypes).forEach(([typeKey, type]) => {
        unmodifiedFunctions[typeKey] = {
            insertRule: type.prototype.insertRule,
            deleteRule: type.prototype.deleteRule,
        };
        type.prototype.insertRule = new Proxy(unmodifiedFunctions[typeKey].insertRule, {
            apply: callbackWrapper((target, thisArg, argumentsList) => {
                const [rule, index] = argumentsList;
                const { id, styleId } = getIdAndStyleId(thisArg.parentStyleSheet, mirror, stylesheetManager.styleMirror);
                if ((id && id !== -1) || (styleId && styleId !== -1)) {
                    styleSheetRuleCb({
                        id,
                        styleId,
                        adds: [
                            {
                                rule,
                                index: [
                                    ...getNestedCSSRulePositions(thisArg),
                                    index || 0,
                                ],
                            },
                        ],
                    });
                }
                return target.apply(thisArg, argumentsList);
            }),
        });
        type.prototype.deleteRule = new Proxy(unmodifiedFunctions[typeKey].deleteRule, {
            apply: callbackWrapper((target, thisArg, argumentsList) => {
                const [index] = argumentsList;
                const { id, styleId } = getIdAndStyleId(thisArg.parentStyleSheet, mirror, stylesheetManager.styleMirror);
                if ((id && id !== -1) || (styleId && styleId !== -1)) {
                    styleSheetRuleCb({
                        id,
                        styleId,
                        removes: [
                            { index: [...getNestedCSSRulePositions(thisArg), index] },
                        ],
                    });
                }
                return target.apply(thisArg, argumentsList);
            }),
        });
    });
    return callbackWrapper(() => {
        win.CSSStyleSheet.prototype.insertRule = insertRule;
        win.CSSStyleSheet.prototype.deleteRule = deleteRule;
        replace && (win.CSSStyleSheet.prototype.replace = replace);
        replaceSync && (win.CSSStyleSheet.prototype.replaceSync = replaceSync);
        Object.entries(supportedNestedCSSRuleTypes).forEach(([typeKey, type]) => {
            type.prototype.insertRule = unmodifiedFunctions[typeKey].insertRule;
            type.prototype.deleteRule = unmodifiedFunctions[typeKey].deleteRule;
        });
    });
}
function initAdoptedStyleSheetObserver({ mirror, stylesheetManager, }, host) {
    var _a, _b, _c;
    let hostId = null;
    if (host.nodeName === '#document')
        hostId = mirror.getId(host);
    else
        hostId = mirror.getId(host.host);
    const patchTarget = host.nodeName === '#document'
        ? (_a = host.defaultView) === null || _a === void 0 ? void 0 : _a.Document
        : (_c = (_b = host.ownerDocument) === null || _b === void 0 ? void 0 : _b.defaultView) === null || _c === void 0 ? void 0 : _c.ShadowRoot;
    const originalPropertyDescriptor = (patchTarget === null || patchTarget === void 0 ? void 0 : patchTarget.prototype)
        ? Object.getOwnPropertyDescriptor(patchTarget === null || patchTarget === void 0 ? void 0 : patchTarget.prototype, 'adoptedStyleSheets')
        : undefined;
    if (hostId === null ||
        hostId === -1 ||
        !patchTarget ||
        !originalPropertyDescriptor)
        return () => {
        };
    Object.defineProperty(host, 'adoptedStyleSheets', {
        configurable: originalPropertyDescriptor.configurable,
        enumerable: originalPropertyDescriptor.enumerable,
        get() {
            var _a;
            return (_a = originalPropertyDescriptor.get) === null || _a === void 0 ? void 0 : _a.call(this);
        },
        set(sheets) {
            var _a;
            const result = (_a = originalPropertyDescriptor.set) === null || _a === void 0 ? void 0 : _a.call(this, sheets);
            if (hostId !== null && hostId !== -1) {
                try {
                    stylesheetManager.adoptStyleSheets(sheets, hostId);
                }
                catch (e) {
                }
            }
            return result;
        },
    });
    return callbackWrapper(() => {
        Object.defineProperty(host, 'adoptedStyleSheets', {
            configurable: originalPropertyDescriptor.configurable,
            enumerable: originalPropertyDescriptor.enumerable,
            get: originalPropertyDescriptor.get,
            set: originalPropertyDescriptor.set,
        });
    });
}
function initStyleDeclarationObserver({ styleDeclarationCb, mirror, ignoreCSSAttributes, stylesheetManager, }, { win }) {
    const setProperty = win.CSSStyleDeclaration.prototype.setProperty;
    win.CSSStyleDeclaration.prototype.setProperty = new Proxy(setProperty, {
        apply: callbackWrapper((target, thisArg, argumentsList) => {
            var _a;
            const [property, value, priority] = argumentsList;
            if (ignoreCSSAttributes.has(property)) {
                return setProperty.apply(thisArg, [property, value, priority]);
            }
            const { id, styleId } = getIdAndStyleId((_a = thisArg.parentRule) === null || _a === void 0 ? void 0 : _a.parentStyleSheet, mirror, stylesheetManager.styleMirror);
            if ((id && id !== -1) || (styleId && styleId !== -1)) {
                styleDeclarationCb({
                    id,
                    styleId,
                    set: {
                        property,
                        value,
                        priority,
                    },
                    index: getNestedCSSRulePositions(thisArg.parentRule),
                });
            }
            return target.apply(thisArg, argumentsList);
        }),
    });
    const removeProperty = win.CSSStyleDeclaration.prototype.removeProperty;
    win.CSSStyleDeclaration.prototype.removeProperty = new Proxy(removeProperty, {
        apply: callbackWrapper((target, thisArg, argumentsList) => {
            var _a;
            const [property] = argumentsList;
            if (ignoreCSSAttributes.has(property)) {
                return removeProperty.apply(thisArg, [property]);
            }
            const { id, styleId } = getIdAndStyleId((_a = thisArg.parentRule) === null || _a === void 0 ? void 0 : _a.parentStyleSheet, mirror, stylesheetManager.styleMirror);
            if ((id && id !== -1) || (styleId && styleId !== -1)) {
                styleDeclarationCb({
                    id,
                    styleId,
                    remove: {
                        property,
                    },
                    index: getNestedCSSRulePositions(thisArg.parentRule),
                });
            }
            return target.apply(thisArg, argumentsList);
        }),
    });
    return callbackWrapper(() => {
        win.CSSStyleDeclaration.prototype.setProperty = setProperty;
        win.CSSStyleDeclaration.prototype.removeProperty = removeProperty;
    });
}
function initMediaInteractionObserver({ mediaInteractionCb, blockClass, blockSelector, unblockSelector, mirror, sampling, doc, }) {
    const handler = callbackWrapper((type) => throttle$1(callbackWrapper((event) => {
        const target = getEventTarget(event);
        if (!target ||
            isBlocked(target, blockClass, blockSelector, unblockSelector, true)) {
            return;
        }
        const { currentTime, volume, muted, playbackRate } = target;
        mediaInteractionCb({
            type,
            id: mirror.getId(target),
            currentTime,
            volume,
            muted,
            playbackRate,
        });
    }), sampling.media || 500));
    const handlers = [
        on('play', handler(0), doc),
        on('pause', handler(1), doc),
        on('seeked', handler(2), doc),
        on('volumechange', handler(3), doc),
        on('ratechange', handler(4), doc),
    ];
    return callbackWrapper(() => {
        handlers.forEach((h) => h());
    });
}
function initFontObserver({ fontCb, doc }) {
    const win = doc.defaultView;
    if (!win) {
        return () => {
        };
    }
    const handlers = [];
    const fontMap = new WeakMap();
    const originalFontFace = win.FontFace;
    win.FontFace = function FontFace(family, source, descriptors) {
        const fontFace = new originalFontFace(family, source, descriptors);
        fontMap.set(fontFace, {
            family,
            buffer: typeof source !== 'string',
            descriptors,
            fontSource: typeof source === 'string'
                ? source
                : JSON.stringify(Array.from(new Uint8Array(source))),
        });
        return fontFace;
    };
    const restoreHandler = patch(doc.fonts, 'add', function (original) {
        return function (fontFace) {
            setTimeout(callbackWrapper(() => {
                const p = fontMap.get(fontFace);
                if (p) {
                    fontCb(p);
                    fontMap.delete(fontFace);
                }
            }), 0);
            return original.apply(this, [fontFace]);
        };
    });
    handlers.push(() => {
        win.FontFace = originalFontFace;
    });
    handlers.push(restoreHandler);
    return callbackWrapper(() => {
        handlers.forEach((h) => h());
    });
}
function initSelectionObserver(param) {
    const { doc, mirror, blockClass, blockSelector, unblockSelector, selectionCb, } = param;
    let collapsed = true;
    const updateSelection = callbackWrapper(() => {
        const selection = doc.getSelection();
        if (!selection || (collapsed && (selection === null || selection === void 0 ? void 0 : selection.isCollapsed)))
            return;
        collapsed = selection.isCollapsed || false;
        const ranges = [];
        const count = selection.rangeCount || 0;
        for (let i = 0; i < count; i++) {
            const range = selection.getRangeAt(i);
            const { startContainer, startOffset, endContainer, endOffset } = range;
            const blocked = isBlocked(startContainer, blockClass, blockSelector, unblockSelector, true) ||
                isBlocked(endContainer, blockClass, blockSelector, unblockSelector, true);
            if (blocked)
                continue;
            ranges.push({
                start: mirror.getId(startContainer),
                startOffset,
                end: mirror.getId(endContainer),
                endOffset,
            });
        }
        selectionCb({ ranges });
    });
    updateSelection();
    return on('selectionchange', updateSelection);
}
function initCustomElementObserver({ doc, customElementCb, }) {
    const win = doc.defaultView;
    if (!win || !win.customElements) {
        return () => {
        };
    }
    const restoreHandler = patch(win.customElements, 'define', function (original) {
        return function (name, constructor, options) {
            try {
                customElementCb({
                    define: {
                        name,
                    },
                });
            }
            catch (e) {
            }
            return original.apply(this, [name, constructor, options]);
        };
    });
    return restoreHandler;
}
function initObservers(o, _hooks = {}) {
    const currentWindow = o.doc.defaultView;
    if (!currentWindow) {
        return () => {
        };
    }
    const mutationObserver = initMutationObserver(o, o.doc);
    const mousemoveHandler = initMoveObserver(o);
    const mouseInteractionHandler = initMouseInteractionObserver(o);
    const scrollHandler = initScrollObserver(o);
    const viewportResizeHandler = initViewportResizeObserver(o, {
        win: currentWindow,
    });
    const inputHandler = initInputObserver(o);
    const mediaInteractionHandler = initMediaInteractionObserver(o);
    const styleSheetObserver = initStyleSheetObserver(o, { win: currentWindow });
    const adoptedStyleSheetObserver = initAdoptedStyleSheetObserver(o, o.doc);
    const styleDeclarationObserver = initStyleDeclarationObserver(o, {
        win: currentWindow,
    });
    const fontObserver = o.collectFonts
        ? initFontObserver(o)
        : () => {
        };
    const selectionObserver = initSelectionObserver(o);
    const customElementObserver = initCustomElementObserver(o);
    return callbackWrapper(() => {
        mutationBuffers.forEach((b) => b.reset());
        mutationObserver.disconnect();
        mousemoveHandler();
        mouseInteractionHandler();
        scrollHandler();
        viewportResizeHandler();
        inputHandler();
        mediaInteractionHandler();
        styleSheetObserver();
        adoptedStyleSheetObserver();
        styleDeclarationObserver();
        fontObserver();
        selectionObserver();
        customElementObserver();
    });
}
function hasNestedCSSRule(prop) {
    return typeof window[prop] !== 'undefined';
}
function canMonkeyPatchNestedCSSRule(prop) {
    return Boolean(typeof window[prop] !== 'undefined' &&
        window[prop].prototype &&
        'insertRule' in window[prop].prototype &&
        'deleteRule' in window[prop].prototype);
}

class CrossOriginIframeMirror {
    constructor(generateIdFn) {
        this.generateIdFn = generateIdFn;
        this.iframeIdToRemoteIdMap = new WeakMap();
        this.iframeRemoteIdToIdMap = new WeakMap();
    }
    getId(iframe, remoteId, idToRemoteMap, remoteToIdMap) {
        const idToRemoteIdMap = idToRemoteMap || this.getIdToRemoteIdMap(iframe);
        const remoteIdToIdMap = remoteToIdMap || this.getRemoteIdToIdMap(iframe);
        let id = idToRemoteIdMap.get(remoteId);
        if (!id) {
            id = this.generateIdFn();
            idToRemoteIdMap.set(remoteId, id);
            remoteIdToIdMap.set(id, remoteId);
        }
        return id;
    }
    getIds(iframe, remoteId) {
        const idToRemoteIdMap = this.getIdToRemoteIdMap(iframe);
        const remoteIdToIdMap = this.getRemoteIdToIdMap(iframe);
        return remoteId.map((id) => this.getId(iframe, id, idToRemoteIdMap, remoteIdToIdMap));
    }
    getRemoteId(iframe, id, map) {
        const remoteIdToIdMap = map || this.getRemoteIdToIdMap(iframe);
        if (typeof id !== 'number')
            return id;
        const remoteId = remoteIdToIdMap.get(id);
        if (!remoteId)
            return -1;
        return remoteId;
    }
    getRemoteIds(iframe, ids) {
        const remoteIdToIdMap = this.getRemoteIdToIdMap(iframe);
        return ids.map((id) => this.getRemoteId(iframe, id, remoteIdToIdMap));
    }
    reset(iframe) {
        if (!iframe) {
            this.iframeIdToRemoteIdMap = new WeakMap();
            this.iframeRemoteIdToIdMap = new WeakMap();
            return;
        }
        this.iframeIdToRemoteIdMap.delete(iframe);
        this.iframeRemoteIdToIdMap.delete(iframe);
    }
    getIdToRemoteIdMap(iframe) {
        let idToRemoteIdMap = this.iframeIdToRemoteIdMap.get(iframe);
        if (!idToRemoteIdMap) {
            idToRemoteIdMap = new Map();
            this.iframeIdToRemoteIdMap.set(iframe, idToRemoteIdMap);
        }
        return idToRemoteIdMap;
    }
    getRemoteIdToIdMap(iframe) {
        let remoteIdToIdMap = this.iframeRemoteIdToIdMap.get(iframe);
        if (!remoteIdToIdMap) {
            remoteIdToIdMap = new Map();
            this.iframeRemoteIdToIdMap.set(iframe, remoteIdToIdMap);
        }
        return remoteIdToIdMap;
    }
}

class IframeManagerNoop {
    constructor() {
        this.crossOriginIframeMirror = new CrossOriginIframeMirror(genId);
        this.crossOriginIframeRootIdMap = new WeakMap();
    }
    addIframe() {
    }
    addLoadListener() {
    }
    attachIframe() {
    }
}
class IframeManager {
    constructor(options) {
        this.iframes = new WeakMap();
        this.crossOriginIframeMap = new WeakMap();
        this.crossOriginIframeMirror = new CrossOriginIframeMirror(genId);
        this.crossOriginIframeRootIdMap = new WeakMap();
        this.mutationCb = options.mutationCb;
        this.wrappedEmit = options.wrappedEmit;
        this.stylesheetManager = options.stylesheetManager;
        this.recordCrossOriginIframes = options.recordCrossOriginIframes;
        this.crossOriginIframeStyleMirror = new CrossOriginIframeMirror(this.stylesheetManager.styleMirror.generateId.bind(this.stylesheetManager.styleMirror));
        this.mirror = options.mirror;
        if (this.recordCrossOriginIframes) {
            window.addEventListener('message', this.handleMessage.bind(this));
        }
    }
    addIframe(iframeEl) {
        this.iframes.set(iframeEl, true);
        if (iframeEl.contentWindow)
            this.crossOriginIframeMap.set(iframeEl.contentWindow, iframeEl);
    }
    addLoadListener(cb) {
        this.loadListener = cb;
    }
    attachIframe(iframeEl, childSn) {
        var _a;
        this.mutationCb({
            adds: [
                {
                    parentId: this.mirror.getId(iframeEl),
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
        if (iframeEl.contentDocument &&
            iframeEl.contentDocument.adoptedStyleSheets &&
            iframeEl.contentDocument.adoptedStyleSheets.length > 0)
            this.stylesheetManager.adoptStyleSheets(iframeEl.contentDocument.adoptedStyleSheets, this.mirror.getId(iframeEl.contentDocument));
    }
    handleMessage(message) {
        const crossOriginMessageEvent = message;
        if (crossOriginMessageEvent.data.type !== 'rrweb' ||
            crossOriginMessageEvent.origin !== crossOriginMessageEvent.data.origin)
            return;
        const iframeSourceWindow = message.source;
        if (!iframeSourceWindow)
            return;
        const iframeEl = this.crossOriginIframeMap.get(message.source);
        if (!iframeEl)
            return;
        const transformedEvent = this.transformCrossOriginEvent(iframeEl, crossOriginMessageEvent.data.event);
        if (transformedEvent)
            this.wrappedEmit(transformedEvent, crossOriginMessageEvent.data.isCheckout);
    }
    transformCrossOriginEvent(iframeEl, e) {
        var _a;
        switch (e.type) {
            case EventType.FullSnapshot: {
                this.crossOriginIframeMirror.reset(iframeEl);
                this.crossOriginIframeStyleMirror.reset(iframeEl);
                this.replaceIdOnNode(e.data.node, iframeEl);
                const rootId = e.data.node.id;
                this.crossOriginIframeRootIdMap.set(iframeEl, rootId);
                this.patchRootIdOnNode(e.data.node, rootId);
                return {
                    timestamp: e.timestamp,
                    type: EventType.IncrementalSnapshot,
                    data: {
                        source: IncrementalSource.Mutation,
                        adds: [
                            {
                                parentId: this.mirror.getId(iframeEl),
                                nextId: null,
                                node: e.data.node,
                            },
                        ],
                        removes: [],
                        texts: [],
                        attributes: [],
                        isAttachIframe: true,
                    },
                };
            }
            case EventType.Meta:
            case EventType.Load:
            case EventType.DomContentLoaded: {
                return false;
            }
            case EventType.Plugin: {
                return e;
            }
            case EventType.Custom: {
                this.replaceIds(e.data.payload, iframeEl, ['id', 'parentId', 'previousId', 'nextId']);
                return e;
            }
            case EventType.IncrementalSnapshot: {
                switch (e.data.source) {
                    case IncrementalSource.Mutation: {
                        e.data.adds.forEach((n) => {
                            this.replaceIds(n, iframeEl, [
                                'parentId',
                                'nextId',
                                'previousId',
                            ]);
                            this.replaceIdOnNode(n.node, iframeEl);
                            const rootId = this.crossOriginIframeRootIdMap.get(iframeEl);
                            rootId && this.patchRootIdOnNode(n.node, rootId);
                        });
                        e.data.removes.forEach((n) => {
                            this.replaceIds(n, iframeEl, ['parentId', 'id']);
                        });
                        e.data.attributes.forEach((n) => {
                            this.replaceIds(n, iframeEl, ['id']);
                        });
                        e.data.texts.forEach((n) => {
                            this.replaceIds(n, iframeEl, ['id']);
                        });
                        return e;
                    }
                    case IncrementalSource.Drag:
                    case IncrementalSource.TouchMove:
                    case IncrementalSource.MouseMove: {
                        e.data.positions.forEach((p) => {
                            this.replaceIds(p, iframeEl, ['id']);
                        });
                        return e;
                    }
                    case IncrementalSource.ViewportResize: {
                        return false;
                    }
                    case IncrementalSource.MediaInteraction:
                    case IncrementalSource.MouseInteraction:
                    case IncrementalSource.Scroll:
                    case IncrementalSource.CanvasMutation:
                    case IncrementalSource.Input: {
                        this.replaceIds(e.data, iframeEl, ['id']);
                        return e;
                    }
                    case IncrementalSource.StyleSheetRule:
                    case IncrementalSource.StyleDeclaration: {
                        this.replaceIds(e.data, iframeEl, ['id']);
                        this.replaceStyleIds(e.data, iframeEl, ['styleId']);
                        return e;
                    }
                    case IncrementalSource.Font: {
                        return e;
                    }
                    case IncrementalSource.Selection: {
                        e.data.ranges.forEach((range) => {
                            this.replaceIds(range, iframeEl, ['start', 'end']);
                        });
                        return e;
                    }
                    case IncrementalSource.AdoptedStyleSheet: {
                        this.replaceIds(e.data, iframeEl, ['id']);
                        this.replaceStyleIds(e.data, iframeEl, ['styleIds']);
                        (_a = e.data.styles) === null || _a === void 0 ? void 0 : _a.forEach((style) => {
                            this.replaceStyleIds(style, iframeEl, ['styleId']);
                        });
                        return e;
                    }
                }
            }
        }
        return false;
    }
    replace(iframeMirror, obj, iframeEl, keys) {
        for (const key of keys) {
            if (!Array.isArray(obj[key]) && typeof obj[key] !== 'number')
                continue;
            if (Array.isArray(obj[key])) {
                obj[key] = iframeMirror.getIds(iframeEl, obj[key]);
            }
            else {
                obj[key] = iframeMirror.getId(iframeEl, obj[key]);
            }
        }
        return obj;
    }
    replaceIds(obj, iframeEl, keys) {
        return this.replace(this.crossOriginIframeMirror, obj, iframeEl, keys);
    }
    replaceStyleIds(obj, iframeEl, keys) {
        return this.replace(this.crossOriginIframeStyleMirror, obj, iframeEl, keys);
    }
    replaceIdOnNode(node, iframeEl) {
        this.replaceIds(node, iframeEl, ['id', 'rootId']);
        if ('childNodes' in node) {
            node.childNodes.forEach((child) => {
                this.replaceIdOnNode(child, iframeEl);
            });
        }
    }
    patchRootIdOnNode(node, rootId) {
        if (node.type !== NodeType$1.Document && !node.rootId)
            node.rootId = rootId;
        if ('childNodes' in node) {
            node.childNodes.forEach((child) => {
                this.patchRootIdOnNode(child, rootId);
            });
        }
    }
}

class ShadowDomManagerNoop {
    init() {
    }
    addShadowRoot() {
    }
    observeAttachShadow() {
    }
    reset() {
    }
}
class ShadowDomManager {
    constructor(options) {
        this.shadowDoms = new WeakSet();
        this.restoreHandlers = [];
        this.mutationCb = options.mutationCb;
        this.scrollCb = options.scrollCb;
        this.bypassOptions = options.bypassOptions;
        this.mirror = options.mirror;
        this.init();
    }
    init() {
        this.reset();
        this.patchAttachShadow(Element, document);
    }
    addShadowRoot(shadowRoot, doc) {
        if (!isNativeShadowDom(shadowRoot))
            return;
        if (this.shadowDoms.has(shadowRoot))
            return;
        this.shadowDoms.add(shadowRoot);
        const observer = initMutationObserver(Object.assign(Object.assign({}, this.bypassOptions), { doc, mutationCb: this.mutationCb, mirror: this.mirror, shadowDomManager: this }), shadowRoot);
        this.restoreHandlers.push(() => observer.disconnect());
        this.restoreHandlers.push(initScrollObserver(Object.assign(Object.assign({}, this.bypassOptions), { scrollCb: this.scrollCb, doc: shadowRoot, mirror: this.mirror })));
        setTimeout(() => {
            if (shadowRoot.adoptedStyleSheets &&
                shadowRoot.adoptedStyleSheets.length > 0)
                this.bypassOptions.stylesheetManager.adoptStyleSheets(shadowRoot.adoptedStyleSheets, this.mirror.getId(shadowRoot.host));
            this.restoreHandlers.push(initAdoptedStyleSheetObserver({
                mirror: this.mirror,
                stylesheetManager: this.bypassOptions.stylesheetManager,
            }, shadowRoot));
        }, 0);
    }
    observeAttachShadow(iframeElement) {
        if (!iframeElement.contentWindow || !iframeElement.contentDocument)
            return;
        this.patchAttachShadow(iframeElement.contentWindow.Element, iframeElement.contentDocument);
    }
    patchAttachShadow(element, doc) {
        const manager = this;
        this.restoreHandlers.push(patch(element.prototype, 'attachShadow', function (original) {
            return function (option) {
                const shadowRoot = original.call(this, option);
                if (this.shadowRoot && inDom(this))
                    manager.addShadowRoot(this.shadowRoot, doc);
                return shadowRoot;
            };
        }));
    }
    reset() {
        this.restoreHandlers.forEach((handler) => {
            try {
                handler();
            }
            catch (e) {
            }
        });
        this.restoreHandlers = [];
        this.shadowDoms = new WeakSet();
    }
}

class CanvasManagerNoop {
    reset() {
    }
    freeze() {
    }
    unfreeze() {
    }
    lock() {
    }
    unlock() {
    }
}

class StylesheetManager {
    constructor(options) {
        this.trackedLinkElements = new WeakSet();
        this.styleMirror = new StyleSheetMirror();
        this.mutationCb = options.mutationCb;
        this.adoptedStyleSheetCb = options.adoptedStyleSheetCb;
    }
    attachLinkElement(linkEl, childSn) {
        if ('_cssText' in childSn.attributes)
            this.mutationCb({
                adds: [],
                removes: [],
                texts: [],
                attributes: [
                    {
                        id: childSn.id,
                        attributes: childSn
                            .attributes,
                    },
                ],
            });
        this.trackLinkElement(linkEl);
    }
    trackLinkElement(linkEl) {
        if (this.trackedLinkElements.has(linkEl))
            return;
        this.trackedLinkElements.add(linkEl);
        this.trackStylesheetInLinkElement(linkEl);
    }
    adoptStyleSheets(sheets, hostId) {
        if (sheets.length === 0)
            return;
        const adoptedStyleSheetData = {
            id: hostId,
            styleIds: [],
        };
        const styles = [];
        for (const sheet of sheets) {
            let styleId;
            if (!this.styleMirror.has(sheet)) {
                styleId = this.styleMirror.add(sheet);
                styles.push({
                    styleId,
                    rules: Array.from(sheet.rules || CSSRule, (r, index) => ({
                        rule: stringifyRule(r),
                        index,
                    })),
                });
            }
            else
                styleId = this.styleMirror.getId(sheet);
            adoptedStyleSheetData.styleIds.push(styleId);
        }
        if (styles.length > 0)
            adoptedStyleSheetData.styles = styles;
        this.adoptedStyleSheetCb(adoptedStyleSheetData);
    }
    reset() {
        this.styleMirror.reset();
        this.trackedLinkElements = new WeakSet();
    }
    trackStylesheetInLinkElement(linkEl) {
    }
}

class ProcessedNodeManager {
    constructor() {
        this.nodeMap = new WeakMap();
        this.loop = true;
        this.periodicallyClear();
    }
    periodicallyClear() {
        requestAnimationFrame(() => {
            this.clear();
            if (this.loop)
                this.periodicallyClear();
        });
    }
    inOtherBuffer(node, thisBuffer) {
        const buffers = this.nodeMap.get(node);
        return (buffers && Array.from(buffers).some((buffer) => buffer !== thisBuffer));
    }
    add(node, buffer) {
        this.nodeMap.set(node, (this.nodeMap.get(node) || new Set()).add(buffer));
    }
    clear() {
        this.nodeMap = new WeakMap();
    }
    destroy() {
        this.loop = false;
    }
}

function wrapEvent(e) {
    const eWithTime = e;
    eWithTime.timestamp = nowTimestamp();
    return eWithTime;
}
let _takeFullSnapshot;
const mirror = createMirror();
function record(options = {}) {
    const { emit, checkoutEveryNms, checkoutEveryNth, blockClass = 'rr-block', blockSelector = null, unblockSelector = null, ignoreClass = 'rr-ignore', ignoreSelector = null, maskAllText = false, maskTextClass = 'rr-mask', unmaskTextClass = null, maskTextSelector = null, unmaskTextSelector = null, inlineStylesheet = true, maskAllInputs, maskInputOptions: _maskInputOptions, slimDOMOptions: _slimDOMOptions, maskAttributeFn, maskInputFn, maskTextFn, packFn, sampling = {}, dataURLOptions = {}, mousemoveWait, recordCanvas = false, recordCrossOriginIframes = false, recordAfter = options.recordAfter === 'DOMContentLoaded'
        ? options.recordAfter
        : 'load', userTriggeredOnInput = false, collectFonts = false, inlineImages = false, keepIframeSrcFn = () => false, ignoreCSSAttributes = new Set([]), errorHandler, onMutation, getCanvasManager, } = options;
    registerErrorHandler(errorHandler);
    const inEmittingFrame = recordCrossOriginIframes
        ? window.parent === window
        : true;
    let passEmitsToParent = false;
    if (!inEmittingFrame) {
        try {
            if (window.parent.document) {
                passEmitsToParent = false;
            }
        }
        catch (e) {
            passEmitsToParent = true;
        }
    }
    if (inEmittingFrame && !emit) {
        throw new Error('emit function is required');
    }
    if (mousemoveWait !== undefined && sampling.mousemove === undefined) {
        sampling.mousemove = mousemoveWait;
    }
    mirror.reset();
    const maskInputOptions = maskAllInputs === true
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
            radio: true,
            checkbox: true,
        }
        : _maskInputOptions !== undefined
            ? _maskInputOptions
            : {};
    const slimDOMOptions = _slimDOMOptions === true || _slimDOMOptions === 'all'
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
    polyfill();
    let lastFullSnapshotEvent;
    let incrementalSnapshotCount = 0;
    const eventProcessor = (e) => {
        if (packFn &&
            !passEmitsToParent) {
            e = packFn(e);
        }
        return e;
    };
    const wrappedEmit = (e, isCheckout) => {
        var _a;
        if (((_a = mutationBuffers[0]) === null || _a === void 0 ? void 0 : _a.isFrozen()) &&
            e.type !== EventType.FullSnapshot &&
            !(e.type === EventType.IncrementalSnapshot &&
                e.data.source === IncrementalSource.Mutation)) {
            mutationBuffers.forEach((buf) => buf.unfreeze());
        }
        if (inEmittingFrame) {
            emit === null || emit === void 0 ? void 0 : emit(eventProcessor(e), isCheckout);
        }
        else if (passEmitsToParent) {
            const message = {
                type: 'rrweb',
                event: eventProcessor(e),
                origin: window.location.origin,
                isCheckout,
            };
            window.parent.postMessage(message, '*');
        }
        if (e.type === EventType.FullSnapshot) {
            lastFullSnapshotEvent = e;
            incrementalSnapshotCount = 0;
        }
        else if (e.type === EventType.IncrementalSnapshot) {
            if (e.data.source === IncrementalSource.Mutation &&
                e.data.isAttachIframe) {
                return;
            }
            incrementalSnapshotCount++;
            const exceedCount = checkoutEveryNth && incrementalSnapshotCount >= checkoutEveryNth;
            const exceedTime = checkoutEveryNms &&
                e.timestamp - lastFullSnapshotEvent.timestamp > checkoutEveryNms;
            if (exceedCount || exceedTime) {
                takeFullSnapshot(true);
            }
        }
    };
    const wrappedMutationEmit = (m) => {
        wrappedEmit(wrapEvent({
            type: EventType.IncrementalSnapshot,
            data: Object.assign({ source: IncrementalSource.Mutation }, m),
        }));
    };
    const wrappedScrollEmit = (p) => wrappedEmit(wrapEvent({
        type: EventType.IncrementalSnapshot,
        data: Object.assign({ source: IncrementalSource.Scroll }, p),
    }));
    const wrappedCanvasMutationEmit = (p) => wrappedEmit(wrapEvent({
        type: EventType.IncrementalSnapshot,
        data: Object.assign({ source: IncrementalSource.CanvasMutation }, p),
    }));
    const wrappedAdoptedStyleSheetEmit = (a) => wrappedEmit(wrapEvent({
        type: EventType.IncrementalSnapshot,
        data: Object.assign({ source: IncrementalSource.AdoptedStyleSheet }, a),
    }));
    const stylesheetManager = new StylesheetManager({
        mutationCb: wrappedMutationEmit,
        adoptedStyleSheetCb: wrappedAdoptedStyleSheetEmit,
    });
    const iframeManager = typeof __RRWEB_EXCLUDE_IFRAME__ === 'boolean' && __RRWEB_EXCLUDE_IFRAME__
        ? new IframeManagerNoop()
        : new IframeManager({
            mirror,
            mutationCb: wrappedMutationEmit,
            stylesheetManager: stylesheetManager,
            recordCrossOriginIframes,
            wrappedEmit,
        });
    const processedNodeManager = new ProcessedNodeManager();
    const canvasManager = getCanvasManager
        ? getCanvasManager({
            recordCanvas,
            blockClass,
            blockSelector,
            unblockSelector,
            sampling: sampling['canvas'],
            dataURLOptions,
        })
        : new CanvasManagerNoop();
    const shadowDomManager = typeof __RRWEB_EXCLUDE_SHADOW_DOM__ === 'boolean' &&
        __RRWEB_EXCLUDE_SHADOW_DOM__
        ? new ShadowDomManagerNoop()
        : new ShadowDomManager({
            mutationCb: wrappedMutationEmit,
            scrollCb: wrappedScrollEmit,
            bypassOptions: {
                onMutation,
                blockClass,
                blockSelector,
                unblockSelector,
                maskAllText,
                maskTextClass,
                unmaskTextClass,
                maskTextSelector,
                unmaskTextSelector,
                inlineStylesheet,
                maskInputOptions,
                dataURLOptions,
                maskAttributeFn,
                maskTextFn,
                maskInputFn,
                recordCanvas,
                inlineImages,
                sampling,
                slimDOMOptions,
                iframeManager,
                stylesheetManager,
                canvasManager,
                keepIframeSrcFn,
                processedNodeManager,
            },
            mirror,
        });
    const takeFullSnapshot = (isCheckout = false) => {
        wrappedEmit(wrapEvent({
            type: EventType.Meta,
            data: {
                href: window.location.href,
                width: getWindowWidth(),
                height: getWindowHeight(),
            },
        }), isCheckout);
        stylesheetManager.reset();
        shadowDomManager.init();
        mutationBuffers.forEach((buf) => buf.lock());
        const node = snapshot(document, {
            mirror,
            blockClass,
            blockSelector,
            unblockSelector,
            maskAllText,
            maskTextClass,
            unmaskTextClass,
            maskTextSelector,
            unmaskTextSelector,
            inlineStylesheet,
            maskAllInputs: maskInputOptions,
            maskAttributeFn,
            maskInputFn,
            maskTextFn,
            slimDOM: slimDOMOptions,
            dataURLOptions,
            recordCanvas,
            inlineImages,
            onSerialize: (n) => {
                if (isSerializedIframe(n, mirror)) {
                    iframeManager.addIframe(n);
                }
                if (isSerializedStylesheet(n, mirror)) {
                    stylesheetManager.trackLinkElement(n);
                }
                if (hasShadowRoot(n)) {
                    shadowDomManager.addShadowRoot(n.shadowRoot, document);
                }
            },
            onIframeLoad: (iframe, childSn) => {
                iframeManager.attachIframe(iframe, childSn);
                shadowDomManager.observeAttachShadow(iframe);
            },
            onStylesheetLoad: (linkEl, childSn) => {
                stylesheetManager.attachLinkElement(linkEl, childSn);
            },
            keepIframeSrcFn,
        });
        if (!node) {
            return console.warn('Failed to snapshot the document');
        }
        wrappedEmit(wrapEvent({
            type: EventType.FullSnapshot,
            data: {
                node,
                initialOffset: getWindowScroll(window),
            },
        }), isCheckout);
        mutationBuffers.forEach((buf) => buf.unlock());
        if (document.adoptedStyleSheets && document.adoptedStyleSheets.length > 0)
            stylesheetManager.adoptStyleSheets(document.adoptedStyleSheets, mirror.getId(document));
    };
    _takeFullSnapshot = takeFullSnapshot;
    try {
        const handlers = [];
        const observe = (doc) => {
            return callbackWrapper(initObservers)({
                onMutation,
                mutationCb: wrappedMutationEmit,
                mousemoveCb: (positions, source) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: {
                        source,
                        positions,
                    },
                })),
                mouseInteractionCb: (d) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: Object.assign({ source: IncrementalSource.MouseInteraction }, d),
                })),
                scrollCb: wrappedScrollEmit,
                viewportResizeCb: (d) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: Object.assign({ source: IncrementalSource.ViewportResize }, d),
                })),
                inputCb: (v) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: Object.assign({ source: IncrementalSource.Input }, v),
                })),
                mediaInteractionCb: (p) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: Object.assign({ source: IncrementalSource.MediaInteraction }, p),
                })),
                styleSheetRuleCb: (r) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: Object.assign({ source: IncrementalSource.StyleSheetRule }, r),
                })),
                styleDeclarationCb: (r) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: Object.assign({ source: IncrementalSource.StyleDeclaration }, r),
                })),
                canvasMutationCb: wrappedCanvasMutationEmit,
                fontCb: (p) => wrappedEmit(wrapEvent({
                    type: EventType.IncrementalSnapshot,
                    data: Object.assign({ source: IncrementalSource.Font }, p),
                })),
                selectionCb: (p) => {
                    wrappedEmit(wrapEvent({
                        type: EventType.IncrementalSnapshot,
                        data: Object.assign({ source: IncrementalSource.Selection }, p),
                    }));
                },
                customElementCb: (c) => {
                    wrappedEmit(wrapEvent({
                        type: EventType.IncrementalSnapshot,
                        data: Object.assign({ source: IncrementalSource.CustomElement }, c),
                    }));
                },
                blockClass,
                ignoreClass,
                ignoreSelector,
                maskAllText,
                maskTextClass,
                unmaskTextClass,
                maskTextSelector,
                unmaskTextSelector,
                maskInputOptions,
                inlineStylesheet,
                sampling,
                recordCanvas,
                inlineImages,
                userTriggeredOnInput,
                collectFonts,
                doc,
                maskAttributeFn,
                maskInputFn,
                maskTextFn,
                keepIframeSrcFn,
                blockSelector,
                unblockSelector,
                slimDOMOptions,
                dataURLOptions,
                mirror,
                iframeManager,
                stylesheetManager,
                shadowDomManager,
                processedNodeManager,
                canvasManager,
                ignoreCSSAttributes,
                plugins: [],
            }, {});
        };
        iframeManager.addLoadListener((iframeEl) => {
            try {
                handlers.push(observe(iframeEl.contentDocument));
            }
            catch (error) {
                console.warn(error);
            }
        });
        const init = () => {
            takeFullSnapshot();
            handlers.push(observe(document));
        };
        if (document.readyState === 'interactive' ||
            document.readyState === 'complete') {
            init();
        }
        else {
            handlers.push(on('DOMContentLoaded', () => {
                wrappedEmit(wrapEvent({
                    type: EventType.DomContentLoaded,
                    data: {},
                }));
                if (recordAfter === 'DOMContentLoaded')
                    init();
            }));
            handlers.push(on('load', () => {
                wrappedEmit(wrapEvent({
                    type: EventType.Load,
                    data: {},
                }));
                if (recordAfter === 'load')
                    init();
            }, window));
        }
        return () => {
            handlers.forEach((h) => h());
            processedNodeManager.destroy();
            _takeFullSnapshot = undefined;
            unregisterErrorHandler();
        };
    }
    catch (error) {
        console.warn(error);
    }
}
function takeFullSnapshot(isCheckout) {
    if (!_takeFullSnapshot) {
        throw new Error('please take full snapshot after start recording');
    }
    _takeFullSnapshot(isCheckout);
}
record.mirror = mirror;
record.takeFullSnapshot = takeFullSnapshot;

const ReplayEventTypeIncrementalSnapshot = 3;
const ReplayEventTypeCustom = 5;

/**
 * Converts a timestamp to ms, if it was in s, or keeps it as ms.
 */
function timestampToMs(timestamp) {
  const isMs = timestamp > 9999999999;
  return isMs ? timestamp : timestamp * 1000;
}

/**
 * Converts a timestamp to s, if it was in ms, or keeps it as s.
 */
function timestampToS(timestamp) {
  const isMs = timestamp > 9999999999;
  return isMs ? timestamp / 1000 : timestamp;
}

/**
 * Add a breadcrumb event to replay.
 */
function addBreadcrumbEvent(replay, breadcrumb) {
  if (breadcrumb.category === 'sentry.transaction') {
    return;
  }

  if (['ui.click', 'ui.input'].includes(breadcrumb.category )) {
    replay.triggerUserActivity();
  } else {
    replay.checkAndHandleExpiredSession();
  }

  replay.addUpdate(() => {
    void replay.throttledAddEvent({
      type: EventType.Custom,
      // TODO: We were converting from ms to seconds for breadcrumbs, spans,
      // but maybe we should just keep them as milliseconds
      timestamp: (breadcrumb.timestamp || 0) * 1000,
      data: {
        tag: 'breadcrumb',
        // normalize to max. 10 depth and 1_000 properties per object
        payload: utils.normalize(breadcrumb, 10, 1000),
      },
    });

    // Do not flush after console log messages
    return breadcrumb.category === 'console';
  });
}

const INTERACTIVE_SELECTOR = 'button,a';

/** Get the closest interactive parent element, or else return the given element. */
function getClosestInteractive(element) {
  const closestInteractive = element.closest(INTERACTIVE_SELECTOR);
  return closestInteractive || element;
}

/**
 * For clicks, we check if the target is inside of a button or link
 * If so, we use this as the target instead
 * This is useful because if you click on the image in <button><img></button>,
 * The target will be the image, not the button, which we don't want here
 */
function getClickTargetNode(event) {
  const target = getTargetNode(event);

  if (!target || !(target instanceof Element)) {
    return target;
  }

  return getClosestInteractive(target);
}

/** Get the event target node. */
function getTargetNode(event) {
  if (isEventWithTarget(event)) {
    return event.target ;
  }

  return event;
}

function isEventWithTarget(event) {
  return typeof event === 'object' && !!event && 'target' in event;
}

let handlers;

/**
 * Register a handler to be called when `window.open()` is called.
 * Returns a cleanup function.
 */
function onWindowOpen(cb) {
  // Ensure to only register this once
  if (!handlers) {
    handlers = [];
    monkeyPatchWindowOpen();
  }

  handlers.push(cb);

  return () => {
    const pos = handlers ? handlers.indexOf(cb) : -1;
    if (pos > -1) {
      (handlers ).splice(pos, 1);
    }
  };
}

function monkeyPatchWindowOpen() {
  utils.fill(WINDOW, 'open', function (originalWindowOpen) {
    return function (...args) {
      if (handlers) {
        try {
          handlers.forEach(handler => handler());
        } catch (e) {
          // ignore errors in here
        }
      }

      return originalWindowOpen.apply(WINDOW, args);
    };
  });
}

/** Handle a click. */
function handleClick(clickDetector, clickBreadcrumb, node) {
  clickDetector.handleClick(clickBreadcrumb, node);
}

/** A click detector class that can be used to detect slow or rage clicks on elements. */
class ClickDetector  {
  // protected for testing

   constructor(
    replay,
    slowClickConfig,
    // Just for easier testing
    _addBreadcrumbEvent = addBreadcrumbEvent,
  ) {
    this._lastMutation = 0;
    this._lastScroll = 0;
    this._clicks = [];

    // We want everything in s, but options are in ms
    this._timeout = slowClickConfig.timeout / 1000;
    this._threshold = slowClickConfig.threshold / 1000;
    this._scollTimeout = slowClickConfig.scrollTimeout / 1000;
    this._replay = replay;
    this._ignoreSelector = slowClickConfig.ignoreSelector;
    this._addBreadcrumbEvent = _addBreadcrumbEvent;
  }

  /** Register click detection handlers on mutation or scroll. */
   addListeners() {
    const cleanupWindowOpen = onWindowOpen(() => {
      // Treat window.open as mutation
      this._lastMutation = nowInSeconds();
    });

    this._teardown = () => {
      cleanupWindowOpen();

      this._clicks = [];
      this._lastMutation = 0;
      this._lastScroll = 0;
    };
  }

  /** Clean up listeners. */
   removeListeners() {
    if (this._teardown) {
      this._teardown();
    }

    if (this._checkClickTimeout) {
      clearTimeout(this._checkClickTimeout);
    }
  }

  /** @inheritDoc */
   handleClick(breadcrumb, node) {
    if (ignoreElement(node, this._ignoreSelector) || !isClickBreadcrumb(breadcrumb)) {
      return;
    }

    const newClick = {
      timestamp: timestampToS(breadcrumb.timestamp),
      clickBreadcrumb: breadcrumb,
      // Set this to 0 so we know it originates from the click breadcrumb
      clickCount: 0,
      node,
    };

    // If there was a click in the last 1s on the same element, ignore it - only keep a single reference per second
    if (
      this._clicks.some(click => click.node === newClick.node && Math.abs(click.timestamp - newClick.timestamp) < 1)
    ) {
      return;
    }

    this._clicks.push(newClick);

    // If this is the first new click, set a timeout to check for multi clicks
    if (this._clicks.length === 1) {
      this._scheduleCheckClicks();
    }
  }

  /** @inheritDoc */
   registerMutation(timestamp = Date.now()) {
    this._lastMutation = timestampToS(timestamp);
  }

  /** @inheritDoc */
   registerScroll(timestamp = Date.now()) {
    this._lastScroll = timestampToS(timestamp);
  }

  /** @inheritDoc */
   registerClick(element) {
    const node = getClosestInteractive(element);
    this._handleMultiClick(node );
  }

  /** Count multiple clicks on elements. */
   _handleMultiClick(node) {
    this._getClicks(node).forEach(click => {
      click.clickCount++;
    });
  }

  /** Get all pending clicks for a given node. */
   _getClicks(node) {
    return this._clicks.filter(click => click.node === node);
  }

  /** Check the clicks that happened. */
   _checkClicks() {
    const timedOutClicks = [];

    const now = nowInSeconds();

    this._clicks.forEach(click => {
      if (!click.mutationAfter && this._lastMutation) {
        click.mutationAfter = click.timestamp <= this._lastMutation ? this._lastMutation - click.timestamp : undefined;
      }
      if (!click.scrollAfter && this._lastScroll) {
        click.scrollAfter = click.timestamp <= this._lastScroll ? this._lastScroll - click.timestamp : undefined;
      }

      // All of these are in seconds!
      if (click.timestamp + this._timeout <= now) {
        timedOutClicks.push(click);
      }
    });

    // Remove "old" clicks
    for (const click of timedOutClicks) {
      const pos = this._clicks.indexOf(click);

      if (pos > -1) {
        this._generateBreadcrumbs(click);
        this._clicks.splice(pos, 1);
      }
    }

    // Trigger new check, unless no clicks left
    if (this._clicks.length) {
      this._scheduleCheckClicks();
    }
  }

  /** Generate matching breadcrumb(s) for the click. */
   _generateBreadcrumbs(click) {
    const replay = this._replay;
    const hadScroll = click.scrollAfter && click.scrollAfter <= this._scollTimeout;
    const hadMutation = click.mutationAfter && click.mutationAfter <= this._threshold;

    const isSlowClick = !hadScroll && !hadMutation;
    const { clickCount, clickBreadcrumb } = click;

    // Slow click
    if (isSlowClick) {
      // If `mutationAfter` is set, it means a mutation happened after the threshold, but before the timeout
      // If not, it means we just timed out without scroll & mutation
      const timeAfterClickMs = Math.min(click.mutationAfter || this._timeout, this._timeout) * 1000;
      const endReason = timeAfterClickMs < this._timeout * 1000 ? 'mutation' : 'timeout';

      const breadcrumb = {
        type: 'default',
        message: clickBreadcrumb.message,
        timestamp: clickBreadcrumb.timestamp,
        category: 'ui.slowClickDetected',
        data: {
          ...clickBreadcrumb.data,
          url: WINDOW.location.href,
          route: replay.getCurrentRoute(),
          timeAfterClickMs,
          endReason,
          // If clickCount === 0, it means multiClick was not correctly captured here
          // - we still want to send 1 in this case
          clickCount: clickCount || 1,
        },
      };

      this._addBreadcrumbEvent(replay, breadcrumb);
      return;
    }

    // Multi click
    if (clickCount > 1) {
      const breadcrumb = {
        type: 'default',
        message: clickBreadcrumb.message,
        timestamp: clickBreadcrumb.timestamp,
        category: 'ui.multiClick',
        data: {
          ...clickBreadcrumb.data,
          url: WINDOW.location.href,
          route: replay.getCurrentRoute(),
          clickCount,
          metric: true,
        },
      };

      this._addBreadcrumbEvent(replay, breadcrumb);
    }
  }

  /** Schedule to check current clicks. */
   _scheduleCheckClicks() {
    if (this._checkClickTimeout) {
      clearTimeout(this._checkClickTimeout);
    }

    this._checkClickTimeout = setTimeout(() => this._checkClicks(), 1000);
  }
}

const SLOW_CLICK_TAGS = ['A', 'BUTTON', 'INPUT'];

/** exported for tests only */
function ignoreElement(node, ignoreSelector) {
  if (!SLOW_CLICK_TAGS.includes(node.tagName)) {
    return true;
  }

  // If <input> tag, we only want to consider input[type='submit'] & input[type='button']
  if (node.tagName === 'INPUT' && !['submit', 'button'].includes(node.getAttribute('type') || '')) {
    return true;
  }

  // If <a> tag, detect special variants that may not lead to an action
  // If target !== _self, we may open the link somewhere else, which would lead to no action
  // Also, when downloading a file, we may not leave the page, but still not trigger an action
  if (
    node.tagName === 'A' &&
    (node.hasAttribute('download') || (node.hasAttribute('target') && node.getAttribute('target') !== '_self'))
  ) {
    return true;
  }

  if (ignoreSelector && node.matches(ignoreSelector)) {
    return true;
  }

  return false;
}

function isClickBreadcrumb(breadcrumb) {
  return !!(breadcrumb.data && typeof breadcrumb.data.nodeId === 'number' && breadcrumb.timestamp);
}

// This is good enough for us, and is easier to test/mock than `timestampInSeconds`
function nowInSeconds() {
  return Date.now() / 1000;
}

/** Update the click detector based on a recording event of rrweb. */
function updateClickDetectorForRecordingEvent(clickDetector, event) {
  try {
    // note: We only consider incremental snapshots here
    // This means that any full snapshot is ignored for mutation detection - the reason is that we simply cannot know if a mutation happened here.
    // E.g. think that we are buffering, an error happens and we take a full snapshot because we switched to session mode -
    // in this scenario, we would not know if a dead click happened because of the error, which is a key dead click scenario.
    // Instead, by ignoring full snapshots, we have the risk that we generate a false positive
    // (if a mutation _did_ happen but was "swallowed" by the full snapshot)
    // But this should be more unlikely as we'd generally capture the incremental snapshot right away

    if (!isIncrementalEvent(event)) {
      return;
    }

    const { source } = event.data;
    if (source === IncrementalSource.Mutation) {
      clickDetector.registerMutation(event.timestamp);
    }

    if (source === IncrementalSource.Scroll) {
      clickDetector.registerScroll(event.timestamp);
    }

    if (isIncrementalMouseInteraction(event)) {
      const { type, id } = event.data;
      const node = record.mirror.getNode(id);

      if (node instanceof HTMLElement && type === MouseInteractions.Click) {
        clickDetector.registerClick(node);
      }
    }
  } catch (e) {
    // ignore errors here, e.g. if accessing something that does not exist
  }
}

function isIncrementalEvent(event) {
  return event.type === ReplayEventTypeIncrementalSnapshot;
}

function isIncrementalMouseInteraction(
  event,
) {
  return event.data.source === IncrementalSource.MouseInteraction;
}

/**
 * Create a breadcrumb for a replay.
 */
function createBreadcrumb(
  breadcrumb,
) {
  return {
    timestamp: Date.now() / 1000,
    type: 'default',
    ...breadcrumb,
  };
}

var NodeType;
(function (NodeType) {
    NodeType[NodeType["Document"] = 0] = "Document";
    NodeType[NodeType["DocumentType"] = 1] = "DocumentType";
    NodeType[NodeType["Element"] = 2] = "Element";
    NodeType[NodeType["Text"] = 3] = "Text";
    NodeType[NodeType["CDATA"] = 4] = "CDATA";
    NodeType[NodeType["Comment"] = 5] = "Comment";
})(NodeType || (NodeType = {}));

// Note that these are the serialized attributes and not attributes directly on
// the DOM Node. Attributes we are interested in:
const ATTRIBUTES_TO_RECORD = new Set([
  'id',
  'class',
  'aria-label',
  'role',
  'name',
  'alt',
  'title',
  'data-test-id',
  'data-testid',
  'disabled',
  'aria-disabled',
]);

/**
 * Inclusion list of attributes that we want to record from the DOM element
 */
function getAttributesToRecord(attributes) {
  const obj = {};
  for (const key in attributes) {
    if (ATTRIBUTES_TO_RECORD.has(key)) {
      let normalizedKey = key;

      if (key === 'data-testid' || key === 'data-test-id') {
        normalizedKey = 'testId';
      }

      obj[normalizedKey] = attributes[key];
    }
  }

  return obj;
}

const handleDomListener = (
  replay,
) => {
  return (handlerData) => {
    if (!replay.isEnabled()) {
      return;
    }

    const result = handleDom(handlerData);

    if (!result) {
      return;
    }

    const isClick = handlerData.name === 'click';
    const event = isClick ? (handlerData.event ) : undefined;
    // Ignore clicks if ctrl/alt/meta/shift keys are held down as they alter behavior of clicks (e.g. open in new tab)
    if (
      isClick &&
      replay.clickDetector &&
      event &&
      event.target &&
      !event.altKey &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.shiftKey
    ) {
      handleClick(
        replay.clickDetector,
        result ,
        getClickTargetNode(handlerData.event ) ,
      );
    }

    addBreadcrumbEvent(replay, result);
  };
};

/** Get the base DOM breadcrumb. */
function getBaseDomBreadcrumb(target, message) {
  const nodeId = record.mirror.getId(target);
  const node = nodeId && record.mirror.getNode(nodeId);
  const meta = node && record.mirror.getMeta(node);
  const element = meta && isElement(meta) ? meta : null;

  return {
    message,
    data: element
      ? {
          nodeId,
          node: {
            id: nodeId,
            tagName: element.tagName,
            textContent: Array.from(element.childNodes)
              .map((node) => node.type === NodeType.Text && node.textContent)
              .filter(Boolean) // filter out empty values
              .map(text => (text ).trim())
              .join(''),
            attributes: getAttributesToRecord(element.attributes),
          },
        }
      : {},
  };
}

/**
 * An event handler to react to DOM events.
 * Exported for tests.
 */
function handleDom(handlerData) {
  const { target, message } = getDomTarget(handlerData);

  return createBreadcrumb({
    category: `ui.${handlerData.name}`,
    ...getBaseDomBreadcrumb(target, message),
  });
}

function getDomTarget(handlerData) {
  const isClick = handlerData.name === 'click';

  let message;
  let target = null;

  // Accessing event.target can throw (see getsentry/raven-js#838, #768)
  try {
    target = isClick ? getClickTargetNode(handlerData.event ) : getTargetNode(handlerData.event );
    message = utils.htmlTreeAsString(target, { maxStringLength: 200 }) || '<unknown>';
  } catch (e) {
    message = '<unknown>';
  }

  return { target, message };
}

function isElement(node) {
  return node.type === NodeType.Element;
}

/** Handle keyboard events & create breadcrumbs. */
function handleKeyboardEvent(replay, event) {
  if (!replay.isEnabled()) {
    return;
  }

  // Update user activity, but do not restart recording as it can create
  // noisy/low-value replays (e.g. user comes back from idle, hits alt-tab, new
  // session with a single "keydown" breadcrumb is created)
  replay.updateUserActivity();

  const breadcrumb = getKeyboardBreadcrumb(event);

  if (!breadcrumb) {
    return;
  }

  addBreadcrumbEvent(replay, breadcrumb);
}

/** exported only for tests */
function getKeyboardBreadcrumb(event) {
  const { metaKey, shiftKey, ctrlKey, altKey, key, target } = event;

  // never capture for input fields
  if (!target || isInputElement(target ) || !key) {
    return null;
  }

  // Note: We do not consider shift here, as that means "uppercase"
  const hasModifierKey = metaKey || ctrlKey || altKey;
  const isCharacterKey = key.length === 1; // other keys like Escape, Tab, etc have a longer length

  // Do not capture breadcrumb if only a word key is pressed
  // This could leak e.g. user input
  if (!hasModifierKey && isCharacterKey) {
    return null;
  }

  const message = utils.htmlTreeAsString(target, { maxStringLength: 200 }) || '<unknown>';
  const baseBreadcrumb = getBaseDomBreadcrumb(target , message);

  return createBreadcrumb({
    category: 'ui.keyDown',
    message,
    data: {
      ...baseBreadcrumb.data,
      metaKey,
      shiftKey,
      ctrlKey,
      altKey,
      key,
    },
  });
}

function isInputElement(target) {
  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
}

// Map entryType -> function to normalize data for event
const ENTRY_TYPES

 = {
  // @ts-expect-error TODO: entry type does not fit the create* functions entry type
  resource: createResourceEntry,
  paint: createPaintEntry,
  // @ts-expect-error TODO: entry type does not fit the create* functions entry type
  navigation: createNavigationEntry,
};

/**
 * Create replay performance entries from the browser performance entries.
 */
function createPerformanceEntries(
  entries,
) {
  return entries.map(createPerformanceEntry).filter(Boolean) ;
}

function createPerformanceEntry(entry) {
  if (!ENTRY_TYPES[entry.entryType]) {
    return null;
  }

  return ENTRY_TYPES[entry.entryType](entry);
}

function getAbsoluteTime(time) {
  // browserPerformanceTimeOrigin can be undefined if `performance` or
  // `performance.now` doesn't exist, but this is already checked by this integration
  return ((utils.browserPerformanceTimeOrigin || WINDOW.performance.timeOrigin) + time) / 1000;
}

function createPaintEntry(entry) {
  const { duration, entryType, name, startTime } = entry;

  const start = getAbsoluteTime(startTime);
  return {
    type: entryType,
    name,
    start,
    end: start + duration,
    data: undefined,
  };
}

function createNavigationEntry(entry) {
  const {
    entryType,
    name,
    decodedBodySize,
    duration,
    domComplete,
    encodedBodySize,
    domContentLoadedEventStart,
    domContentLoadedEventEnd,
    domInteractive,
    loadEventStart,
    loadEventEnd,
    redirectCount,
    startTime,
    transferSize,
    type,
  } = entry;

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
      decodedBodySize,
      encodedBodySize,
      duration,
      domInteractive,
      domContentLoadedEventStart,
      domContentLoadedEventEnd,
      loadEventStart,
      loadEventEnd,
      domComplete,
      redirectCount,
    },
  };
}

function createResourceEntry(
  entry,
) {
  const {
    entryType,
    initiatorType,
    name,
    responseEnd,
    startTime,
    decodedBodySize,
    encodedBodySize,
    responseStatus,
    transferSize,
  } = entry;

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
      statusCode: responseStatus,
      decodedBodySize,
      encodedBodySize,
    },
  };
}

/**
 * Add a LCP event to the replay based on an LCP metric.
 */
function getLargestContentfulPaint(metric

) {
  const entries = metric.entries;
  const lastEntry = entries[entries.length - 1] ;
  const element = lastEntry ? lastEntry.element : undefined;

  const value = metric.value;

  const end = getAbsoluteTime(value);

  const data = {
    type: 'largest-contentful-paint',
    name: 'largest-contentful-paint',
    start: end,
    end,
    data: {
      value,
      size: value,
      nodeId: element ? record.mirror.getId(element) : undefined,
    },
  };

  return data;
}

/**
 * Sets up a PerformanceObserver to listen to all performance entry types.
 * Returns a callback to stop observing.
 */
function setupPerformanceObserver(replay) {
  function addPerformanceEntry(entry) {
    // It is possible for entries to come up multiple times
    if (!replay.performanceEntries.includes(entry)) {
      replay.performanceEntries.push(entry);
    }
  }

  function onEntries({ entries }) {
    entries.forEach(addPerformanceEntry);
  }

  const clearCallbacks = [];

  (['navigation', 'paint', 'resource'] ).forEach(type => {
    clearCallbacks.push(tracing.addPerformanceInstrumentationHandler(type, onEntries));
  });

  clearCallbacks.push(
    tracing.addLcpInstrumentationHandler(({ metric }) => {
      replay.replayPerformanceEntries.push(getLargestContentfulPaint(metric));
    }),
  );

  // A callback to cleanup all handlers
  return () => {
    clearCallbacks.forEach(clearCallback => clearCallback());
  };
}

/**
 * This serves as a build time flag that will be true by default, but false in non-debug builds or if users replace `__SENTRY_DEBUG__` in their generated code.
 *
 * ATTENTION: This constant must never cross package boundaries (i.e. be exported) to guarantee that it can be used for tree shaking.
 */
const DEBUG_BUILD = (typeof __SENTRY_DEBUG__ === 'undefined' || __SENTRY_DEBUG__);

const r = `var t=Uint8Array,n=Uint16Array,r=Int32Array,e=new t([0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0,0,0,0]),i=new t([0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13,0,0]),a=new t([16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15]),s=function(t,e){for(var i=new n(31),a=0;a<31;++a)i[a]=e+=1<<t[a-1];var s=new r(i[30]);for(a=1;a<30;++a)for(var o=i[a];o<i[a+1];++o)s[o]=o-i[a]<<5|a;return{b:i,r:s}},o=s(e,2),f=o.b,h=o.r;f[28]=258,h[258]=28;for(var l=s(i,0).r,u=new n(32768),c=0;c<32768;++c){var v=(43690&c)>>1|(21845&c)<<1;v=(61680&(v=(52428&v)>>2|(13107&v)<<2))>>4|(3855&v)<<4,u[c]=((65280&v)>>8|(255&v)<<8)>>1}var d=function(t,r,e){for(var i=t.length,a=0,s=new n(r);a<i;++a)t[a]&&++s[t[a]-1];var o,f=new n(r);for(a=1;a<r;++a)f[a]=f[a-1]+s[a-1]<<1;if(e){o=new n(1<<r);var h=15-r;for(a=0;a<i;++a)if(t[a])for(var l=a<<4|t[a],c=r-t[a],v=f[t[a]-1]++<<c,d=v|(1<<c)-1;v<=d;++v)o[u[v]>>h]=l}else for(o=new n(i),a=0;a<i;++a)t[a]&&(o[a]=u[f[t[a]-1]++]>>15-t[a]);return o},g=new t(288);for(c=0;c<144;++c)g[c]=8;for(c=144;c<256;++c)g[c]=9;for(c=256;c<280;++c)g[c]=7;for(c=280;c<288;++c)g[c]=8;var w=new t(32);for(c=0;c<32;++c)w[c]=5;var p=d(g,9,0),y=d(w,5,0),m=function(t){return(t+7)/8|0},b=function(n,r,e){return(null==r||r<0)&&(r=0),(null==e||e>n.length)&&(e=n.length),new t(n.subarray(r,e))},M=["unexpected EOF","invalid block type","invalid length/literal","invalid distance","stream finished","no stream handler",,"no callback","invalid UTF-8 data","extra field too long","date not in range 1980-2099","filename too long","stream finishing","invalid zip data"],E=function(t,n,r){var e=new Error(n||M[t]);if(e.code=t,Error.captureStackTrace&&Error.captureStackTrace(e,E),!r)throw e;return e},z=function(t,n,r){r<<=7&n;var e=n/8|0;t[e]|=r,t[e+1]|=r>>8},A=function(t,n,r){r<<=7&n;var e=n/8|0;t[e]|=r,t[e+1]|=r>>8,t[e+2]|=r>>16},_=function(r,e){for(var i=[],a=0;a<r.length;++a)r[a]&&i.push({s:a,f:r[a]});var s=i.length,o=i.slice();if(!s)return{t:F,l:0};if(1==s){var f=new t(i[0].s+1);return f[i[0].s]=1,{t:f,l:1}}i.sort((function(t,n){return t.f-n.f})),i.push({s:-1,f:25001});var h=i[0],l=i[1],u=0,c=1,v=2;for(i[0]={s:-1,f:h.f+l.f,l:h,r:l};c!=s-1;)h=i[i[u].f<i[v].f?u++:v++],l=i[u!=c&&i[u].f<i[v].f?u++:v++],i[c++]={s:-1,f:h.f+l.f,l:h,r:l};var d=o[0].s;for(a=1;a<s;++a)o[a].s>d&&(d=o[a].s);var g=new n(d+1),w=x(i[c-1],g,0);if(w>e){a=0;var p=0,y=w-e,m=1<<y;for(o.sort((function(t,n){return g[n.s]-g[t.s]||t.f-n.f}));a<s;++a){var b=o[a].s;if(!(g[b]>e))break;p+=m-(1<<w-g[b]),g[b]=e}for(p>>=y;p>0;){var M=o[a].s;g[M]<e?p-=1<<e-g[M]++-1:++a}for(;a>=0&&p;--a){var E=o[a].s;g[E]==e&&(--g[E],++p)}w=e}return{t:new t(g),l:w}},x=function(t,n,r){return-1==t.s?Math.max(x(t.l,n,r+1),x(t.r,n,r+1)):n[t.s]=r},D=function(t){for(var r=t.length;r&&!t[--r];);for(var e=new n(++r),i=0,a=t[0],s=1,o=function(t){e[i++]=t},f=1;f<=r;++f)if(t[f]==a&&f!=r)++s;else{if(!a&&s>2){for(;s>138;s-=138)o(32754);s>2&&(o(s>10?s-11<<5|28690:s-3<<5|12305),s=0)}else if(s>3){for(o(a),--s;s>6;s-=6)o(8304);s>2&&(o(s-3<<5|8208),s=0)}for(;s--;)o(a);s=1,a=t[f]}return{c:e.subarray(0,i),n:r}},T=function(t,n){for(var r=0,e=0;e<n.length;++e)r+=t[e]*n[e];return r},k=function(t,n,r){var e=r.length,i=m(n+2);t[i]=255&e,t[i+1]=e>>8,t[i+2]=255^t[i],t[i+3]=255^t[i+1];for(var a=0;a<e;++a)t[i+a+4]=r[a];return 8*(i+4+e)},C=function(t,r,s,o,f,h,l,u,c,v,m){z(r,m++,s),++f[256];for(var b=_(f,15),M=b.t,E=b.l,x=_(h,15),C=x.t,U=x.l,F=D(M),I=F.c,S=F.n,L=D(C),O=L.c,j=L.n,q=new n(19),B=0;B<I.length;++B)++q[31&I[B]];for(B=0;B<O.length;++B)++q[31&O[B]];for(var G=_(q,7),H=G.t,J=G.l,K=19;K>4&&!H[a[K-1]];--K);var N,P,Q,R,V=v+5<<3,W=T(f,g)+T(h,w)+l,X=T(f,M)+T(h,C)+l+14+3*K+T(q,H)+2*q[16]+3*q[17]+7*q[18];if(c>=0&&V<=W&&V<=X)return k(r,m,t.subarray(c,c+v));if(z(r,m,1+(X<W)),m+=2,X<W){N=d(M,E,0),P=M,Q=d(C,U,0),R=C;var Y=d(H,J,0);z(r,m,S-257),z(r,m+5,j-1),z(r,m+10,K-4),m+=14;for(B=0;B<K;++B)z(r,m+3*B,H[a[B]]);m+=3*K;for(var Z=[I,O],$=0;$<2;++$){var tt=Z[$];for(B=0;B<tt.length;++B){var nt=31&tt[B];z(r,m,Y[nt]),m+=H[nt],nt>15&&(z(r,m,tt[B]>>5&127),m+=tt[B]>>12)}}}else N=p,P=g,Q=y,R=w;for(B=0;B<u;++B){var rt=o[B];if(rt>255){A(r,m,N[(nt=rt>>18&31)+257]),m+=P[nt+257],nt>7&&(z(r,m,rt>>23&31),m+=e[nt]);var et=31&rt;A(r,m,Q[et]),m+=R[et],et>3&&(A(r,m,rt>>5&8191),m+=i[et])}else A(r,m,N[rt]),m+=P[rt]}return A(r,m,N[256]),m+P[256]},U=new r([65540,131080,131088,131104,262176,1048704,1048832,2114560,2117632]),F=new t(0),I=function(){for(var t=new Int32Array(256),n=0;n<256;++n){for(var r=n,e=9;--e;)r=(1&r&&-306674912)^r>>>1;t[n]=r}return t}(),S=function(){var t=1,n=0;return{p:function(r){for(var e=t,i=n,a=0|r.length,s=0;s!=a;){for(var o=Math.min(s+2655,a);s<o;++s)i+=e+=r[s];e=(65535&e)+15*(e>>16),i=(65535&i)+15*(i>>16)}t=e,n=i},d:function(){return(255&(t%=65521))<<24|(65280&t)<<8|(255&(n%=65521))<<8|n>>8}}},L=function(a,s,o,f,u){if(!u&&(u={l:1},s.dictionary)){var c=s.dictionary.subarray(-32768),v=new t(c.length+a.length);v.set(c),v.set(a,c.length),a=v,u.w=c.length}return function(a,s,o,f,u,c){var v=c.z||a.length,d=new t(f+v+5*(1+Math.ceil(v/7e3))+u),g=d.subarray(f,d.length-u),w=c.l,p=7&(c.r||0);if(s){p&&(g[0]=c.r>>3);for(var y=U[s-1],M=y>>13,E=8191&y,z=(1<<o)-1,A=c.p||new n(32768),_=c.h||new n(z+1),x=Math.ceil(o/3),D=2*x,T=function(t){return(a[t]^a[t+1]<<x^a[t+2]<<D)&z},F=new r(25e3),I=new n(288),S=new n(32),L=0,O=0,j=c.i||0,q=0,B=c.w||0,G=0;j+2<v;++j){var H=T(j),J=32767&j,K=_[H];if(A[J]=K,_[H]=J,B<=j){var N=v-j;if((L>7e3||q>24576)&&(N>423||!w)){p=C(a,g,0,F,I,S,O,q,G,j-G,p),q=L=O=0,G=j;for(var P=0;P<286;++P)I[P]=0;for(P=0;P<30;++P)S[P]=0}var Q=2,R=0,V=E,W=J-K&32767;if(N>2&&H==T(j-W))for(var X=Math.min(M,N)-1,Y=Math.min(32767,j),Z=Math.min(258,N);W<=Y&&--V&&J!=K;){if(a[j+Q]==a[j+Q-W]){for(var $=0;$<Z&&a[j+$]==a[j+$-W];++$);if($>Q){if(Q=$,R=W,$>X)break;var tt=Math.min(W,$-2),nt=0;for(P=0;P<tt;++P){var rt=j-W+P&32767,et=rt-A[rt]&32767;et>nt&&(nt=et,K=rt)}}}W+=(J=K)-(K=A[J])&32767}if(R){F[q++]=268435456|h[Q]<<18|l[R];var it=31&h[Q],at=31&l[R];O+=e[it]+i[at],++I[257+it],++S[at],B=j+Q,++L}else F[q++]=a[j],++I[a[j]]}}for(j=Math.max(j,B);j<v;++j)F[q++]=a[j],++I[a[j]];p=C(a,g,w,F,I,S,O,q,G,j-G,p),w||(c.r=7&p|g[p/8|0]<<3,p-=7,c.h=_,c.p=A,c.i=j,c.w=B)}else{for(j=c.w||0;j<v+w;j+=65535){var st=j+65535;st>=v&&(g[p/8|0]=w,st=v),p=k(g,p+1,a.subarray(j,st))}c.i=v}return b(d,0,f+m(p)+u)}(a,null==s.level?6:s.level,null==s.mem?Math.ceil(1.5*Math.max(8,Math.min(13,Math.log(a.length)))):12+s.mem,o,f,u)},O=function(t,n,r){for(;r;++n)t[n]=r,r>>>=8},j=function(){function n(n,r){if("function"==typeof n&&(r=n,n={}),this.ondata=r,this.o=n||{},this.s={l:0,i:32768,w:32768,z:32768},this.b=new t(98304),this.o.dictionary){var e=this.o.dictionary.subarray(-32768);this.b.set(e,32768-e.length),this.s.i=32768-e.length}}return n.prototype.p=function(t,n){this.ondata(L(t,this.o,0,0,this.s),n)},n.prototype.push=function(n,r){this.ondata||E(5),this.s.l&&E(4);var e=n.length+this.s.z;if(e>this.b.length){if(e>2*this.b.length-32768){var i=new t(-32768&e);i.set(this.b.subarray(0,this.s.z)),this.b=i}var a=this.b.length-this.s.z;a&&(this.b.set(n.subarray(0,a),this.s.z),this.s.z=this.b.length,this.p(this.b,!1)),this.b.set(this.b.subarray(-32768)),this.b.set(n.subarray(a),32768),this.s.z=n.length-a+32768,this.s.i=32766,this.s.w=32768}else this.b.set(n,this.s.z),this.s.z+=n.length;this.s.l=1&r,(this.s.z>this.s.w+8191||r)&&(this.p(this.b,r||!1),this.s.w=this.s.i,this.s.i-=2)},n}();function q(t,n){n||(n={});var r=function(){var t=-1;return{p:function(n){for(var r=t,e=0;e<n.length;++e)r=I[255&r^n[e]]^r>>>8;t=r},d:function(){return~t}}}(),e=t.length;r.p(t);var i,a=L(t,n,10+((i=n).filename?i.filename.length+1:0),8),s=a.length;return function(t,n){var r=n.filename;if(t[0]=31,t[1]=139,t[2]=8,t[8]=n.level<2?4:9==n.level?2:0,t[9]=3,0!=n.mtime&&O(t,4,Math.floor(new Date(n.mtime||Date.now())/1e3)),r){t[3]=8;for(var e=0;e<=r.length;++e)t[e+10]=r.charCodeAt(e)}}(a,n),O(a,s-8,r.d()),O(a,s-4,e),a}var B=function(){function t(t,n){this.c=S(),this.v=1,j.call(this,t,n)}return t.prototype.push=function(t,n){this.c.p(t),j.prototype.push.call(this,t,n)},t.prototype.p=function(t,n){var r=L(t,this.o,this.v&&(this.o.dictionary?6:2),n&&4,this.s);this.v&&(function(t,n){var r=n.level,e=0==r?0:r<6?1:9==r?3:2;if(t[0]=120,t[1]=e<<6|(n.dictionary&&32),t[1]|=31-(t[0]<<8|t[1])%31,n.dictionary){var i=S();i.p(n.dictionary),O(t,2,i.d())}}(r,this.o),this.v=0),n&&O(r,r.length-4,this.c.d()),this.ondata(r,n)},t}(),G="undefined"!=typeof TextEncoder&&new TextEncoder,H="undefined"!=typeof TextDecoder&&new TextDecoder;try{H.decode(F,{stream:!0})}catch(t){}var J=function(){function t(t){this.ondata=t}return t.prototype.push=function(t,n){this.ondata||E(5),this.d&&E(4),this.ondata(K(t),this.d=n||!1)},t}();function K(n,r){if(r){for(var e=new t(n.length),i=0;i<n.length;++i)e[i]=n.charCodeAt(i);return e}if(G)return G.encode(n);var a=n.length,s=new t(n.length+(n.length>>1)),o=0,f=function(t){s[o++]=t};for(i=0;i<a;++i){if(o+5>s.length){var h=new t(o+8+(a-i<<1));h.set(s),s=h}var l=n.charCodeAt(i);l<128||r?f(l):l<2048?(f(192|l>>6),f(128|63&l)):l>55295&&l<57344?(f(240|(l=65536+(1047552&l)|1023&n.charCodeAt(++i))>>18),f(128|l>>12&63),f(128|l>>6&63),f(128|63&l)):(f(224|l>>12),f(128|l>>6&63),f(128|63&l))}return b(s,0,o)}const N=new class{constructor(){this._init()}clear(){this._init()}addEvent(t){if(!t)throw new Error("Adding invalid event");const n=this._hasEvents?",":"";this.stream.push(n+t),this._hasEvents=!0}finish(){this.stream.push("]",!0);const t=function(t){let n=0;for(let r=0,e=t.length;r<e;r++)n+=t[r].length;const r=new Uint8Array(n);for(let n=0,e=0,i=t.length;n<i;n++){const i=t[n];r.set(i,e),e+=i.length}return r}(this._deflatedData);return this._init(),t}_init(){this._hasEvents=!1,this._deflatedData=[],this.deflate=new B,this.deflate.ondata=(t,n)=>{this._deflatedData.push(t)},this.stream=new J(((t,n)=>{this.deflate.push(t,n)})),this.stream.push("[")}},P={clear:()=>{N.clear()},addEvent:t=>N.addEvent(t),finish:()=>N.finish(),compress:t=>function(t){return q(K(t))}(t)};addEventListener("message",(function(t){const n=t.data.method,r=t.data.id,e=t.data.arg;if(n in P&&"function"==typeof P[n])try{const t=P[n](e);postMessage({id:r,method:n,success:!0,response:t})}catch(t){postMessage({id:r,method:n,success:!1,response:t.message}),console.error(t)}})),postMessage({id:void 0,method:"init",success:!0,response:void 0});`;

function e(){const e=new Blob([r]);return URL.createObjectURL(e)}

/**
 * Log a message in debug mode, and add a breadcrumb when _experiment.traceInternals is enabled.
 */
function logInfo(message, shouldAddBreadcrumb) {
  if (!DEBUG_BUILD) {
    return;
  }

  utils.logger.info(message);

  if (shouldAddBreadcrumb) {
    addBreadcrumb(message);
  }
}

/**
 * Log a message, and add a breadcrumb in the next tick.
 * This is necessary when the breadcrumb may be added before the replay is initialized.
 */
function logInfoNextTick(message, shouldAddBreadcrumb) {
  if (!DEBUG_BUILD) {
    return;
  }

  utils.logger.info(message);

  if (shouldAddBreadcrumb) {
    // Wait a tick here to avoid race conditions for some initial logs
    // which may be added before replay is initialized
    setTimeout(() => {
      addBreadcrumb(message);
    }, 0);
  }
}

function addBreadcrumb(message) {
  const hub = core.getCurrentHub();
  hub.addBreadcrumb(
    {
      category: 'console',
      data: {
        logger: 'replay',
      },
      level: 'info',
      message,
    },
    { level: 'info' },
  );
}

/** This error indicates that the event buffer size exceeded the limit.. */
class EventBufferSizeExceededError extends Error {
   constructor() {
    super(`Event buffer exceeded maximum size of ${REPLAY_MAX_EVENT_BUFFER_SIZE}.`);
  }
}

/**
 * A basic event buffer that does not do any compression.
 * Used as fallback if the compression worker cannot be loaded or is disabled.
 */
class EventBufferArray  {
  /** All the events that are buffered to be sent. */

  /** @inheritdoc */

   constructor() {
    this.events = [];
    this._totalSize = 0;
    this.hasCheckout = false;
  }

  /** @inheritdoc */
   get hasEvents() {
    return this.events.length > 0;
  }

  /** @inheritdoc */
   get type() {
    return 'sync';
  }

  /** @inheritdoc */
   destroy() {
    this.events = [];
  }

  /** @inheritdoc */
   async addEvent(event) {
    const eventSize = JSON.stringify(event).length;
    this._totalSize += eventSize;
    if (this._totalSize > REPLAY_MAX_EVENT_BUFFER_SIZE) {
      throw new EventBufferSizeExceededError();
    }

    this.events.push(event);
  }

  /** @inheritdoc */
   finish() {
    return new Promise(resolve => {
      // Make a copy of the events array reference and immediately clear the
      // events member so that we do not lose new events while uploading
      // attachment.
      const eventsRet = this.events;
      this.clear();
      resolve(JSON.stringify(eventsRet));
    });
  }

  /** @inheritdoc */
   clear() {
    this.events = [];
    this._totalSize = 0;
    this.hasCheckout = false;
  }

  /** @inheritdoc */
   getEarliestTimestamp() {
    const timestamp = this.events.map(event => event.timestamp).sort()[0];

    if (!timestamp) {
      return null;
    }

    return timestampToMs(timestamp);
  }
}

/**
 * Event buffer that uses a web worker to compress events.
 * Exported only for testing.
 */
class WorkerHandler {

   constructor(worker) {
    this._worker = worker;
    this._id = 0;
  }

  /**
   * Ensure the worker is ready (or not).
   * This will either resolve when the worker is ready, or reject if an error occured.
   */
   ensureReady() {
    // Ensure we only check once
    if (this._ensureReadyPromise) {
      return this._ensureReadyPromise;
    }

    this._ensureReadyPromise = new Promise((resolve, reject) => {
      this._worker.addEventListener(
        'message',
        ({ data }) => {
          if ((data ).success) {
            resolve();
          } else {
            reject();
          }
        },
        { once: true },
      );

      this._worker.addEventListener(
        'error',
        error => {
          reject(error);
        },
        { once: true },
      );
    });

    return this._ensureReadyPromise;
  }

  /**
   * Destroy the worker.
   */
   destroy() {
    logInfo('[Replay] Destroying compression worker');
    this._worker.terminate();
  }

  /**
   * Post message to worker and wait for response before resolving promise.
   */
   postMessage(method, arg) {
    const id = this._getAndIncrementId();

    return new Promise((resolve, reject) => {
      const listener = ({ data }) => {
        const response = data ;
        if (response.method !== method) {
          return;
        }

        // There can be multiple listeners for a single method, the id ensures
        // that the response matches the caller.
        if (response.id !== id) {
          return;
        }

        // At this point, we'll always want to remove listener regardless of result status
        this._worker.removeEventListener('message', listener);

        if (!response.success) {
          // TODO: Do some error handling, not sure what
          DEBUG_BUILD && utils.logger.error('[Replay]', response.response);

          reject(new Error('Error in compression worker'));
          return;
        }

        resolve(response.response );
      };

      // Note: we can't use `once` option because it's possible it needs to
      // listen to multiple messages
      this._worker.addEventListener('message', listener);
      this._worker.postMessage({ id, method, arg });
    });
  }

  /** Get the current ID and increment it for the next call. */
   _getAndIncrementId() {
    return this._id++;
  }
}

/**
 * Event buffer that uses a web worker to compress events.
 * Exported only for testing.
 */
class EventBufferCompressionWorker  {
  /** @inheritdoc */

   constructor(worker) {
    this._worker = new WorkerHandler(worker);
    this._earliestTimestamp = null;
    this._totalSize = 0;
    this.hasCheckout = false;
  }

  /** @inheritdoc */
   get hasEvents() {
    return !!this._earliestTimestamp;
  }

  /** @inheritdoc */
   get type() {
    return 'worker';
  }

  /**
   * Ensure the worker is ready (or not).
   * This will either resolve when the worker is ready, or reject if an error occured.
   */
   ensureReady() {
    return this._worker.ensureReady();
  }

  /**
   * Destroy the event buffer.
   */
   destroy() {
    this._worker.destroy();
  }

  /**
   * Add an event to the event buffer.
   *
   * Returns true if event was successfuly received and processed by worker.
   */
   addEvent(event) {
    const timestamp = timestampToMs(event.timestamp);
    if (!this._earliestTimestamp || timestamp < this._earliestTimestamp) {
      this._earliestTimestamp = timestamp;
    }

    const data = JSON.stringify(event);
    this._totalSize += data.length;

    if (this._totalSize > REPLAY_MAX_EVENT_BUFFER_SIZE) {
      return Promise.reject(new EventBufferSizeExceededError());
    }

    return this._sendEventToWorker(data);
  }

  /**
   * Finish the event buffer and return the compressed data.
   */
   finish() {
    return this._finishRequest();
  }

  /** @inheritdoc */
   clear() {
    this._earliestTimestamp = null;
    this._totalSize = 0;
    this.hasCheckout = false;

    // We do not wait on this, as we assume the order of messages is consistent for the worker
    void this._worker.postMessage('clear');
  }

  /** @inheritdoc */
   getEarliestTimestamp() {
    return this._earliestTimestamp;
  }

  /**
   * Send the event to the worker.
   */
   _sendEventToWorker(data) {
    return this._worker.postMessage('addEvent', data);
  }

  /**
   * Finish the request and return the compressed data from the worker.
   */
   async _finishRequest() {
    const response = await this._worker.postMessage('finish');

    this._earliestTimestamp = null;
    this._totalSize = 0;

    return response;
  }
}

/**
 * This proxy will try to use the compression worker, and fall back to use the simple buffer if an error occurs there.
 * This can happen e.g. if the worker cannot be loaded.
 * Exported only for testing.
 */
class EventBufferProxy  {

   constructor(worker) {
    this._fallback = new EventBufferArray();
    this._compression = new EventBufferCompressionWorker(worker);
    this._used = this._fallback;

    this._ensureWorkerIsLoadedPromise = this._ensureWorkerIsLoaded();
  }

  /** @inheritdoc */
   get type() {
    return this._used.type;
  }

  /** @inheritDoc */
   get hasEvents() {
    return this._used.hasEvents;
  }

  /** @inheritdoc */
   get hasCheckout() {
    return this._used.hasCheckout;
  }
  /** @inheritdoc */
   set hasCheckout(value) {
    this._used.hasCheckout = value;
  }

  /** @inheritDoc */
   destroy() {
    this._fallback.destroy();
    this._compression.destroy();
  }

  /** @inheritdoc */
   clear() {
    return this._used.clear();
  }

  /** @inheritdoc */
   getEarliestTimestamp() {
    return this._used.getEarliestTimestamp();
  }

  /**
   * Add an event to the event buffer.
   *
   * Returns true if event was successfully added.
   */
   addEvent(event) {
    return this._used.addEvent(event);
  }

  /** @inheritDoc */
   async finish() {
    // Ensure the worker is loaded, so the sent event is compressed
    await this.ensureWorkerIsLoaded();

    return this._used.finish();
  }

  /** Ensure the worker has loaded. */
   ensureWorkerIsLoaded() {
    return this._ensureWorkerIsLoadedPromise;
  }

  /** Actually check if the worker has been loaded. */
   async _ensureWorkerIsLoaded() {
    try {
      await this._compression.ensureReady();
    } catch (error) {
      // If the worker fails to load, we fall back to the simple buffer.
      // Nothing more to do from our side here
      logInfo('[Replay] Failed to load the compression worker, falling back to simple buffer');
      return;
    }

    // Now we need to switch over the array buffer to the compression worker
    await this._switchToCompressionWorker();
  }

  /** Switch the used buffer to the compression worker. */
   async _switchToCompressionWorker() {
    const { events, hasCheckout } = this._fallback;

    const addEventPromises = [];
    for (const event of events) {
      addEventPromises.push(this._compression.addEvent(event));
    }

    this._compression.hasCheckout = hasCheckout;

    // We switch over to the new buffer immediately - any further events will be added
    // after the previously buffered ones
    this._used = this._compression;

    // Wait for original events to be re-added before resolving
    try {
      await Promise.all(addEventPromises);
    } catch (error) {
      DEBUG_BUILD && utils.logger.warn('[Replay] Failed to add events when switching buffers.', error);
    }
  }
}

/**
 * Create an event buffer for replays.
 */
function createEventBuffer({
  useCompression,
  workerUrl: customWorkerUrl,
}) {
  if (
    useCompression &&
    // eslint-disable-next-line no-restricted-globals
    window.Worker
  ) {
    const worker = _loadWorker(customWorkerUrl);

    if (worker) {
      return worker;
    }
  }

  logInfo('[Replay] Using simple buffer');
  return new EventBufferArray();
}

function _loadWorker(customWorkerUrl) {
  try {
    const workerUrl = customWorkerUrl || _getWorkerUrl();

    if (!workerUrl) {
      return;
    }

    logInfo(`[Replay] Using compression worker${customWorkerUrl ? ` from ${customWorkerUrl}` : ''}`);
    const worker = new Worker(workerUrl);
    return new EventBufferProxy(worker);
  } catch (error) {
    logInfo('[Replay] Failed to create compression worker');
    // Fall back to use simple event buffer array
  }
}

function _getWorkerUrl() {
  if (typeof __SENTRY_EXCLUDE_REPLAY_WORKER__ === 'undefined' || !__SENTRY_EXCLUDE_REPLAY_WORKER__) {
    return e();
  }

  return '';
}

/** If sessionStorage is available. */
function hasSessionStorage() {
  try {
    // This can throw, e.g. when being accessed in a sandboxed iframe
    return 'sessionStorage' in WINDOW && !!WINDOW.sessionStorage;
  } catch (e) {
    return false;
  }
}

/**
 * Removes the session from Session Storage and unsets session in replay instance
 */
function clearSession(replay) {
  deleteSession();
  replay.session = undefined;
}

/**
 * Deletes a session from storage
 */
function deleteSession() {
  if (!hasSessionStorage()) {
    return;
  }

  try {
    WINDOW.sessionStorage.removeItem(REPLAY_SESSION_KEY);
  } catch (e) {
    // Ignore potential SecurityError exceptions
  }
}

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

/**
 * Get a session with defaults & applied sampling.
 */
function makeSession(session) {
  const now = Date.now();
  const id = session.id || utils.uuid4();
  // Note that this means we cannot set a started/lastActivity of `0`, but this should not be relevant outside of tests.
  const started = session.started || now;
  const lastActivity = session.lastActivity || now;
  const segmentId = session.segmentId || 0;
  const sampled = session.sampled;
  const previousSessionId = session.previousSessionId;

  return {
    id,
    started,
    lastActivity,
    segmentId,
    sampled,
    previousSessionId,
  };
}

/**
 * Save a session to session storage.
 */
function saveSession(session) {
  if (!hasSessionStorage()) {
    return;
  }

  try {
    WINDOW.sessionStorage.setItem(REPLAY_SESSION_KEY, JSON.stringify(session));
  } catch (e) {
    // Ignore potential SecurityError exceptions
  }
}

/**
 * Get the sampled status for a session based on sample rates & current sampled status.
 */
function getSessionSampleType(sessionSampleRate, allowBuffering) {
  return isSampled(sessionSampleRate) ? 'session' : allowBuffering ? 'buffer' : false;
}

/**
 * Create a new session, which in its current implementation is a Sentry event
 * that all replays will be saved to as attachments. Currently, we only expect
 * one of these Sentry events per "replay session".
 */
function createSession(
  { sessionSampleRate, allowBuffering, stickySession = false },
  { previousSessionId } = {},
) {
  const sampled = getSessionSampleType(sessionSampleRate, allowBuffering);
  const session = makeSession({
    sampled,
    previousSessionId,
  });

  if (stickySession) {
    saveSession(session);
  }

  return session;
}

/**
 * Fetches a session from storage
 */
function fetchSession(traceInternals) {
  if (!hasSessionStorage()) {
    return null;
  }

  try {
    // This can throw if cookies are disabled
    const sessionStringFromStorage = WINDOW.sessionStorage.getItem(REPLAY_SESSION_KEY);

    if (!sessionStringFromStorage) {
      return null;
    }

    const sessionObj = JSON.parse(sessionStringFromStorage) ;

    logInfoNextTick('[Replay] Loading existing session', traceInternals);

    return makeSession(sessionObj);
  } catch (e) {
    return null;
  }
}

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

/**
 * Checks to see if session is expired
 */
function isSessionExpired(
  session,
  {
    maxReplayDuration,
    sessionIdleExpire,
    targetTime = Date.now(),
  },
) {
  return (
    // First, check that maximum session length has not been exceeded
    isExpired(session.started, maxReplayDuration, targetTime) ||
    // check that the idle timeout has not been exceeded (i.e. user has
    // performed an action within the last `sessionIdleExpire` ms)
    isExpired(session.lastActivity, sessionIdleExpire, targetTime)
  );
}

/** If the session should be refreshed or not. */
function shouldRefreshSession(
  session,
  { sessionIdleExpire, maxReplayDuration },
) {
  // If not expired, all good, just keep the session
  if (!isSessionExpired(session, { sessionIdleExpire, maxReplayDuration })) {
    return false;
  }

  // If we are buffering & haven't ever flushed yet, always continue
  if (session.sampled === 'buffer' && session.segmentId === 0) {
    return false;
  }

  return true;
}

/**
 * Get or create a session, when initializing the replay.
 * Returns a session that may be unsampled.
 */
function loadOrCreateSession(
  {
    traceInternals,
    sessionIdleExpire,
    maxReplayDuration,
    previousSessionId,
  }

,
  sessionOptions,
) {
  const existingSession = sessionOptions.stickySession && fetchSession(traceInternals);

  // No session exists yet, just create a new one
  if (!existingSession) {
    logInfoNextTick('[Replay] Creating new session', traceInternals);
    return createSession(sessionOptions, { previousSessionId });
  }

  if (!shouldRefreshSession(existingSession, { sessionIdleExpire, maxReplayDuration })) {
    return existingSession;
  }

  logInfoNextTick('[Replay] Session in sessionStorage is expired, creating new one...');
  return createSession(sessionOptions, { previousSessionId: existingSession.id });
}

function isCustomEvent(event) {
  return event.type === EventType.Custom;
}

/**
 * Add an event to the event buffer.
 * In contrast to `addEvent`, this does not return a promise & does not wait for the adding of the event to succeed/fail.
 * Instead this returns `true` if we tried to add the event, else false.
 * It returns `false` e.g. if we are paused, disabled, or out of the max replay duration.
 *
 * `isCheckout` is true if this is either the very first event, or an event triggered by `checkoutEveryNms`.
 */
function addEventSync(replay, event, isCheckout) {
  if (!shouldAddEvent(replay, event)) {
    return false;
  }

  void _addEvent(replay, event, isCheckout);

  return true;
}

/**
 * Add an event to the event buffer.
 * Resolves to `null` if no event was added, else to `void`.
 *
 * `isCheckout` is true if this is either the very first event, or an event triggered by `checkoutEveryNms`.
 */
function addEvent(
  replay,
  event,
  isCheckout,
) {
  if (!shouldAddEvent(replay, event)) {
    return Promise.resolve(null);
  }

  return _addEvent(replay, event, isCheckout);
}

async function _addEvent(
  replay,
  event,
  isCheckout,
) {
  if (!replay.eventBuffer) {
    return null;
  }

  try {
    if (isCheckout && replay.recordingMode === 'buffer') {
      replay.eventBuffer.clear();
    }

    if (isCheckout) {
      replay.eventBuffer.hasCheckout = true;
    }

    const replayOptions = replay.getOptions();

    const eventAfterPossibleCallback = maybeApplyCallback(event, replayOptions.beforeAddRecordingEvent);

    if (!eventAfterPossibleCallback) {
      return;
    }

    return await replay.eventBuffer.addEvent(eventAfterPossibleCallback);
  } catch (error) {
    const reason = error && error instanceof EventBufferSizeExceededError ? 'addEventSizeExceeded' : 'addEvent';

    DEBUG_BUILD && utils.logger.error(error);
    await replay.stop({ reason });

    const client = core.getClient();

    if (client) {
      client.recordDroppedEvent('internal_sdk_error', 'replay');
    }
  }
}

/** Exported only for tests. */
function shouldAddEvent(replay, event) {
  if (!replay.eventBuffer || replay.isPaused() || !replay.isEnabled()) {
    return false;
  }

  const timestampInMs = timestampToMs(event.timestamp);

  // Throw out events that happen more than 5 minutes ago. This can happen if
  // page has been left open and idle for a long period of time and user
  // comes back to trigger a new session. The performance entries rely on
  // `performance.timeOrigin`, which is when the page first opened.
  if (timestampInMs + replay.timeouts.sessionIdlePause < Date.now()) {
    return false;
  }

  // Throw out events that are +60min from the initial timestamp
  if (timestampInMs > replay.getContext().initialTimestamp + replay.getOptions().maxReplayDuration) {
    logInfo(
      `[Replay] Skipping event with timestamp ${timestampInMs} because it is after maxReplayDuration`,
      replay.getOptions()._experiments.traceInternals,
    );
    return false;
  }

  return true;
}

function maybeApplyCallback(
  event,
  callback,
) {
  try {
    if (typeof callback === 'function' && isCustomEvent(event)) {
      return callback(event);
    }
  } catch (error) {
    DEBUG_BUILD &&
      utils.logger.error('[Replay] An error occured in the `beforeAddRecordingEvent` callback, skipping the event...', error);
    return null;
  }

  return event;
}

/** If the event is an error event */
function isErrorEvent(event) {
  return !event.type;
}

/** If the event is a transaction event */
function isTransactionEvent(event) {
  return event.type === 'transaction';
}

/** If the event is an replay event */
function isReplayEvent(event) {
  return event.type === 'replay_event';
}

/** If the event is a feedback event */
function isFeedbackEvent(event) {
  return event.type === 'feedback';
}

/**
 * Returns a listener to be added to `client.on('afterSendErrorEvent, listener)`.
 */
function handleAfterSendEvent(replay) {
  // Custom transports may still be returning `Promise<void>`, which means we cannot expect the status code to be available there
  // TODO (v8): remove this check as it will no longer be necessary
  const enforceStatusCode = isBaseTransportSend();

  return (event, sendResponse) => {
    if (!replay.isEnabled() || (!isErrorEvent(event) && !isTransactionEvent(event))) {
      return;
    }

    const statusCode = sendResponse && sendResponse.statusCode;

    // We only want to do stuff on successful error sending, otherwise you get error replays without errors attached
    // If not using the base transport, we allow `undefined` response (as a custom transport may not implement this correctly yet)
    // If we do use the base transport, we skip if we encountered an non-OK status code
    if (enforceStatusCode && (!statusCode || statusCode < 200 || statusCode >= 300)) {
      return;
    }

    if (isTransactionEvent(event)) {
      handleTransactionEvent(replay, event);
      return;
    }

    handleErrorEvent(replay, event);
  };
}

function handleTransactionEvent(replay, event) {
  const replayContext = replay.getContext();

  // Collect traceIds in _context regardless of `recordingMode`
  // In error mode, _context gets cleared on every checkout
  // We limit to max. 100 transactions linked
  if (event.contexts && event.contexts.trace && event.contexts.trace.trace_id && replayContext.traceIds.size < 100) {
    replayContext.traceIds.add(event.contexts.trace.trace_id );
  }
}

function handleErrorEvent(replay, event) {
  const replayContext = replay.getContext();

  // Add error to list of errorIds of replay. This is ok to do even if not
  // sampled because context will get reset at next checkout.
  // XXX: There is also a race condition where it's possible to capture an
  // error to Sentry before Replay SDK has loaded, but response returns after
  // it was loaded, and this gets called.
  // We limit to max. 100 errors linked
  if (event.event_id && replayContext.errorIds.size < 100) {
    replayContext.errorIds.add(event.event_id);
  }

  // If error event is tagged with replay id it means it was sampled (when in buffer mode)
  // Need to be very careful that this does not cause an infinite loop
  if (replay.recordingMode !== 'buffer' || !event.tags || !event.tags.replayId) {
    return;
  }

  const { beforeErrorSampling } = replay.getOptions();
  if (typeof beforeErrorSampling === 'function' && !beforeErrorSampling(event)) {
    return;
  }

  setTimeout(() => {
    // Capture current event buffer as new replay
    void replay.sendBufferedReplayOrFlush();
  });
}

function isBaseTransportSend() {
  const client = core.getClient();
  if (!client) {
    return false;
  }

  const transport = client.getTransport();
  if (!transport) {
    return false;
  }

  return (
    (transport.send ).__sentry__baseTransport__ || false
  );
}

/**
 * Returns true if we think the given event is an error originating inside of rrweb.
 */
function isRrwebError(event, hint) {
  if (event.type || !event.exception || !event.exception.values || !event.exception.values.length) {
    return false;
  }

  // @ts-expect-error this may be set by rrweb when it finds errors
  if (hint.originalException && hint.originalException.__rrweb__) {
    return true;
  }

  return false;
}

/**
 * Add a feedback breadcrumb event to replay.
 */
function addFeedbackBreadcrumb(replay, event) {
  replay.triggerUserActivity();
  replay.addUpdate(() => {
    if (!event.timestamp) {
      // Ignore events that don't have timestamps (this shouldn't happen, more of a typing issue)
      // Return true here so that we don't flush
      return true;
    }

    void replay.throttledAddEvent({
      type: EventType.Custom,
      timestamp: event.timestamp * 1000,
      data: {
        timestamp: event.timestamp,
        tag: 'breadcrumb',
        payload: {
          category: 'sentry.feedback',
          data: {
            feedbackId: event.event_id,
          },
        },
      },
    });

    return false;
  });
}

/**
 * Determine if event should be sampled (only applies in buffer mode).
 * When an event is captured by `hanldleGlobalEvent`, when in buffer mode
 * we determine if we want to sample the error or not.
 */
function shouldSampleForBufferEvent(replay, event) {
  if (replay.recordingMode !== 'buffer') {
    return false;
  }

  // ignore this error because otherwise we could loop indefinitely with
  // trying to capture replay and failing
  if (event.message === UNABLE_TO_SEND_REPLAY) {
    return false;
  }

  // Require the event to be an error event & to have an exception
  if (!event.exception || event.type) {
    return false;
  }

  return isSampled(replay.getOptions().errorSampleRate);
}

/**
 * Returns a listener to be added to `addEventProcessor(listener)`.
 */
function handleGlobalEventListener(
  replay,
  includeAfterSendEventHandling = false,
) {
  const afterSendHandler = includeAfterSendEventHandling ? handleAfterSendEvent(replay) : undefined;

  return Object.assign(
    (event, hint) => {
      // Do nothing if replay has been disabled
      if (!replay.isEnabled()) {
        return event;
      }

      if (isReplayEvent(event)) {
        // Replays have separate set of breadcrumbs, do not include breadcrumbs
        // from core SDK
        delete event.breadcrumbs;
        return event;
      }

      // We only want to handle errors, transactions, and feedbacks, nothing else
      if (!isErrorEvent(event) && !isTransactionEvent(event) && !isFeedbackEvent(event)) {
        return event;
      }

      // Ensure we do not add replay_id if the session is expired
      const isSessionActive = replay.checkAndHandleExpiredSession();
      if (!isSessionActive) {
        return event;
      }

      if (isFeedbackEvent(event)) {
        void replay.flush();
        event.contexts.feedback.replay_id = replay.getSessionId();
        // Add a replay breadcrumb for this piece of feedback
        addFeedbackBreadcrumb(replay, event);
        return event;
      }

      // Unless `captureExceptions` is enabled, we want to ignore errors coming from rrweb
      // As there can be a bunch of stuff going wrong in internals there, that we don't want to bubble up to users
      if (isRrwebError(event, hint) && !replay.getOptions()._experiments.captureExceptions) {
        DEBUG_BUILD && utils.logger.log('[Replay] Ignoring error from rrweb internals', event);
        return null;
      }

      // When in buffer mode, we decide to sample here.
      // Later, in `handleAfterSendEvent`, if the replayId is set, we know that we sampled
      // And convert the buffer session to a full session
      const isErrorEventSampled = shouldSampleForBufferEvent(replay, event);

      // Tag errors if it has been sampled in buffer mode, or if it is session mode
      // Only tag transactions if in session mode
      const shouldTagReplayId = isErrorEventSampled || replay.recordingMode === 'session';

      if (shouldTagReplayId) {
        event.tags = { ...event.tags, replayId: replay.getSessionId() };
      }

      // In cases where a custom client is used that does not support the new hooks (yet),
      // we manually call this hook method here
      if (afterSendHandler) {
        // Pretend the error had a 200 response so we always capture it
        afterSendHandler(event, { statusCode: 200 });
      }

      return event;
    },
    { id: 'Replay' },
  );
}

/**
 * Create a "span" for each performance entry.
 */
function createPerformanceSpans(
  replay,
  entries,
) {
  return entries.map(({ type, start, end, name, data }) => {
    const response = replay.throttledAddEvent({
      type: EventType.Custom,
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
    });

    // If response is a string, it means its either THROTTLED or SKIPPED
    return typeof response === 'string' ? Promise.resolve(null) : response;
  });
}

function handleHistory(handlerData) {
  const { from, to } = handlerData;

  const now = Date.now() / 1000;

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
 * Returns a listener to be added to `addHistoryInstrumentationHandler(listener)`.
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
      createPerformanceSpans(replay, [result]);
      // Returning false to flush
      return false;
    });
  };
}

/**
 * Check whether a given request URL should be filtered out. This is so we
 * don't log Sentry ingest requests.
 */
function shouldFilterRequest(replay, url) {
  // If we enabled the `traceInternals` experiment, we want to trace everything
  if (DEBUG_BUILD && replay.getOptions()._experiments.traceInternals) {
    return false;
  }

  return core.isSentryRequestUrl(url, core.getCurrentHub());
}

/** Add a performance entry breadcrumb */
function addNetworkBreadcrumb(
  replay,
  result,
) {
  if (!replay.isEnabled()) {
    return;
  }

  if (result === null) {
    return;
  }

  if (shouldFilterRequest(replay, result.name)) {
    return;
  }

  replay.addUpdate(() => {
    createPerformanceSpans(replay, [result]);
    // Returning true will cause `addUpdate` to not flush
    // We do not want network requests to cause a flush. This will prevent
    // recurring/polling requests from keeping the replay session alive.
    return true;
  });
}

/** only exported for tests */
function handleFetch(handlerData) {
  const { startTimestamp, endTimestamp, fetchData, response } = handlerData;

  if (!endTimestamp) {
    return null;
  }

  // This is only used as a fallback, so we know the body sizes are never set here
  const { method, url } = fetchData;

  return {
    type: 'resource.fetch',
    start: startTimestamp / 1000,
    end: endTimestamp / 1000,
    name: url,
    data: {
      method,
      statusCode: response ? (response ).status : undefined,
    },
  };
}

/**
 * Returns a listener to be added to `addFetchInstrumentationHandler(listener)`.
 */
function handleFetchSpanListener(replay) {
  return (handlerData) => {
    if (!replay.isEnabled()) {
      return;
    }

    const result = handleFetch(handlerData);

    addNetworkBreadcrumb(replay, result);
  };
}

/** only exported for tests */
function handleXhr(handlerData) {
  const { startTimestamp, endTimestamp, xhr } = handlerData;

  const sentryXhrData = xhr[utils.SENTRY_XHR_DATA_KEY];

  if (!startTimestamp || !endTimestamp || !sentryXhrData) {
    return null;
  }

  // This is only used as a fallback, so we know the body sizes are never set here
  const { method, url, status_code: statusCode } = sentryXhrData;

  if (url === undefined) {
    return null;
  }

  return {
    type: 'resource.xhr',
    name: url,
    start: startTimestamp / 1000,
    end: endTimestamp / 1000,
    data: {
      method,
      statusCode,
    },
  };
}

/**
 * Returns a listener to be added to `addXhrInstrumentationHandler(listener)`.
 */
function handleXhrSpanListener(replay) {
  return (handlerData) => {
    if (!replay.isEnabled()) {
      return;
    }

    const result = handleXhr(handlerData);

    addNetworkBreadcrumb(replay, result);
  };
}

/** Get the size of a body. */
function getBodySize(
  body,
  textEncoder,
) {
  if (!body) {
    return undefined;
  }

  try {
    if (typeof body === 'string') {
      return textEncoder.encode(body).length;
    }

    if (body instanceof URLSearchParams) {
      return textEncoder.encode(body.toString()).length;
    }

    if (body instanceof FormData) {
      const formDataStr = _serializeFormData(body);
      return textEncoder.encode(formDataStr).length;
    }

    if (body instanceof Blob) {
      return body.size;
    }

    if (body instanceof ArrayBuffer) {
      return body.byteLength;
    }

    // Currently unhandled types: ArrayBufferView, ReadableStream
  } catch (e) {
    // just return undefined
  }

  return undefined;
}

/** Convert a Content-Length header to number/undefined.  */
function parseContentLengthHeader(header) {
  if (!header) {
    return undefined;
  }

  const size = parseInt(header, 10);
  return isNaN(size) ? undefined : size;
}

/** Get the string representation of a body. */
function getBodyString(body) {
  try {
    if (typeof body === 'string') {
      return [body];
    }

    if (body instanceof URLSearchParams) {
      return [body.toString()];
    }

    if (body instanceof FormData) {
      return [_serializeFormData(body)];
    }

    if (!body) {
      return [undefined];
    }
  } catch (e2) {
    DEBUG_BUILD && utils.logger.warn('[Replay] Failed to serialize body', body);
    return [undefined, 'BODY_PARSE_ERROR'];
  }

  DEBUG_BUILD && utils.logger.info('[Replay] Skipping network body because of body type', body);

  return [undefined, 'UNPARSEABLE_BODY_TYPE'];
}

/** Merge a warning into an existing network request/response. */
function mergeWarning(
  info,
  warning,
) {
  if (!info) {
    return {
      headers: {},
      size: undefined,
      _meta: {
        warnings: [warning],
      },
    };
  }

  const newMeta = { ...info._meta };
  const existingWarnings = newMeta.warnings || [];
  newMeta.warnings = [...existingWarnings, warning];

  info._meta = newMeta;
  return info;
}

/** Convert ReplayNetworkRequestData to a PerformanceEntry. */
function makeNetworkReplayBreadcrumb(
  type,
  data,
) {
  if (!data) {
    return null;
  }

  const { startTimestamp, endTimestamp, url, method, statusCode, request, response } = data;

  const result = {
    type,
    start: startTimestamp / 1000,
    end: endTimestamp / 1000,
    name: url,
    data: utils.dropUndefinedKeys({
      method,
      statusCode,
      request,
      response,
    }),
  };

  return result;
}

/** Build the request or response part of a replay network breadcrumb that was skipped. */
function buildSkippedNetworkRequestOrResponse(bodySize) {
  return {
    headers: {},
    size: bodySize,
    _meta: {
      warnings: ['URL_SKIPPED'],
    },
  };
}

/** Build the request or response part of a replay network breadcrumb. */
function buildNetworkRequestOrResponse(
  headers,
  bodySize,
  body,
) {
  if (!bodySize && Object.keys(headers).length === 0) {
    return undefined;
  }

  if (!bodySize) {
    return {
      headers,
    };
  }

  if (!body) {
    return {
      headers,
      size: bodySize,
    };
  }

  const info = {
    headers,
    size: bodySize,
  };

  const { body: normalizedBody, warnings } = normalizeNetworkBody(body);
  info.body = normalizedBody;
  if (warnings && warnings.length > 0) {
    info._meta = {
      warnings,
    };
  }

  return info;
}

/** Filter a set of headers */
function getAllowedHeaders(headers, allowedHeaders) {
  return Object.keys(headers).reduce((filteredHeaders, key) => {
    const normalizedKey = key.toLowerCase();
    // Avoid putting empty strings into the headers
    if (allowedHeaders.includes(normalizedKey) && headers[key]) {
      filteredHeaders[normalizedKey] = headers[key];
    }
    return filteredHeaders;
  }, {});
}

function _serializeFormData(formData) {
  // This is a bit simplified, but gives us a decent estimate
  // This converts e.g. { name: 'Anne Smith', age: 13 } to 'name=Anne+Smith&age=13'
  // @ts-expect-error passing FormData to URLSearchParams actually works
  return new URLSearchParams(formData).toString();
}

function normalizeNetworkBody(body)

 {
  if (!body || typeof body !== 'string') {
    return {
      body,
    };
  }

  const exceedsSizeLimit = body.length > NETWORK_BODY_MAX_SIZE;
  const isProbablyJson = _strIsProbablyJson(body);

  if (exceedsSizeLimit) {
    const truncatedBody = body.slice(0, NETWORK_BODY_MAX_SIZE);

    if (isProbablyJson) {
      return {
        body: truncatedBody,
        warnings: ['MAYBE_JSON_TRUNCATED'],
      };
    }

    return {
      body: `${truncatedBody}…`,
      warnings: ['TEXT_TRUNCATED'],
    };
  }

  if (isProbablyJson) {
    try {
      const jsonBody = JSON.parse(body);
      return {
        body: jsonBody,
      };
    } catch (e3) {
      // fall back to just send the body as string
    }
  }

  return {
    body,
  };
}

function _strIsProbablyJson(str) {
  const first = str[0];
  const last = str[str.length - 1];

  // Simple check: If this does not start & end with {} or [], it's not JSON
  return (first === '[' && last === ']') || (first === '{' && last === '}');
}

/** Match an URL against a list of strings/Regex. */
function urlMatches(url, urls) {
  const fullUrl = getFullUrl(url);

  return utils.stringMatchesSomePattern(fullUrl, urls);
}

/** exported for tests */
function getFullUrl(url, baseURI = WINDOW.document.baseURI) {
  // Short circuit for common cases:
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith(WINDOW.location.origin)) {
    return url;
  }
  const fixedUrl = new URL(url, baseURI);

  // If these do not match, we are not dealing with a relative URL, so just return it
  if (fixedUrl.origin !== new URL(baseURI).origin) {
    return url;
  }

  const fullUrl = fixedUrl.href;

  // Remove trailing slashes, if they don't match the original URL
  if (!url.endsWith('/') && fullUrl.endsWith('/')) {
    return fullUrl.slice(0, -1);
  }

  return fullUrl;
}

/**
 * Capture a fetch breadcrumb to a replay.
 * This adds additional data (where approriate).
 */
async function captureFetchBreadcrumbToReplay(
  breadcrumb,
  hint,
  options

,
) {
  try {
    const data = await _prepareFetchData(breadcrumb, hint, options);

    // Create a replay performance entry from this breadcrumb
    const result = makeNetworkReplayBreadcrumb('resource.fetch', data);
    addNetworkBreadcrumb(options.replay, result);
  } catch (error) {
    DEBUG_BUILD && utils.logger.error('[Replay] Failed to capture fetch breadcrumb', error);
  }
}

/**
 * Enrich a breadcrumb with additional data.
 * This has to be sync & mutate the given breadcrumb,
 * as the breadcrumb is afterwards consumed by other handlers.
 */
function enrichFetchBreadcrumb(
  breadcrumb,
  hint,
  options,
) {
  const { input, response } = hint;

  const body = input ? _getFetchRequestArgBody(input) : undefined;
  const reqSize = getBodySize(body, options.textEncoder);

  const resSize = response ? parseContentLengthHeader(response.headers.get('content-length')) : undefined;

  if (reqSize !== undefined) {
    breadcrumb.data.request_body_size = reqSize;
  }
  if (resSize !== undefined) {
    breadcrumb.data.response_body_size = resSize;
  }
}

async function _prepareFetchData(
  breadcrumb,
  hint,
  options

,
) {
  const now = Date.now();
  const { startTimestamp = now, endTimestamp = now } = hint;

  const {
    url,
    method,
    status_code: statusCode = 0,
    request_body_size: requestBodySize,
    response_body_size: responseBodySize,
  } = breadcrumb.data;

  const captureDetails =
    urlMatches(url, options.networkDetailAllowUrls) && !urlMatches(url, options.networkDetailDenyUrls);

  const request = captureDetails
    ? _getRequestInfo(options, hint.input, requestBodySize)
    : buildSkippedNetworkRequestOrResponse(requestBodySize);
  const response = await _getResponseInfo(captureDetails, options, hint.response, responseBodySize);

  return {
    startTimestamp,
    endTimestamp,
    url,
    method,
    statusCode,
    request,
    response,
  };
}

function _getRequestInfo(
  { networkCaptureBodies, networkRequestHeaders },
  input,
  requestBodySize,
) {
  const headers = input ? getRequestHeaders(input, networkRequestHeaders) : {};

  if (!networkCaptureBodies) {
    return buildNetworkRequestOrResponse(headers, requestBodySize, undefined);
  }

  // We only want to transmit string or string-like bodies
  const requestBody = _getFetchRequestArgBody(input);
  const [bodyStr, warning] = getBodyString(requestBody);
  const data = buildNetworkRequestOrResponse(headers, requestBodySize, bodyStr);

  if (warning) {
    return mergeWarning(data, warning);
  }

  return data;
}

/** Exported only for tests. */
async function _getResponseInfo(
  captureDetails,
  {
    networkCaptureBodies,
    textEncoder,
    networkResponseHeaders,
  }

,
  response,
  responseBodySize,
) {
  if (!captureDetails && responseBodySize !== undefined) {
    return buildSkippedNetworkRequestOrResponse(responseBodySize);
  }

  const headers = response ? getAllHeaders(response.headers, networkResponseHeaders) : {};

  if (!response || (!networkCaptureBodies && responseBodySize !== undefined)) {
    return buildNetworkRequestOrResponse(headers, responseBodySize, undefined);
  }

  const [bodyText, warning] = await _parseFetchResponseBody(response);
  const result = getResponseData(bodyText, {
    networkCaptureBodies,
    textEncoder,
    responseBodySize,
    captureDetails,
    headers,
  });

  if (warning) {
    return mergeWarning(result, warning);
  }

  return result;
}

function getResponseData(
  bodyText,
  {
    networkCaptureBodies,
    textEncoder,
    responseBodySize,
    captureDetails,
    headers,
  }

,
) {
  try {
    const size =
      bodyText && bodyText.length && responseBodySize === undefined
        ? getBodySize(bodyText, textEncoder)
        : responseBodySize;

    if (!captureDetails) {
      return buildSkippedNetworkRequestOrResponse(size);
    }

    if (networkCaptureBodies) {
      return buildNetworkRequestOrResponse(headers, size, bodyText);
    }

    return buildNetworkRequestOrResponse(headers, size, undefined);
  } catch (error) {
    DEBUG_BUILD && utils.logger.warn('[Replay] Failed to serialize response body', error);
    // fallback
    return buildNetworkRequestOrResponse(headers, responseBodySize, undefined);
  }
}

async function _parseFetchResponseBody(response) {
  const res = _tryCloneResponse(response);

  if (!res) {
    return [undefined, 'BODY_PARSE_ERROR'];
  }

  try {
    const text = await _tryGetResponseText(res);
    return [text];
  } catch (error) {
    DEBUG_BUILD && utils.logger.warn('[Replay] Failed to get text body from response', error);
    return [undefined, 'BODY_PARSE_ERROR'];
  }
}

function _getFetchRequestArgBody(fetchArgs = []) {
  // We only support getting the body from the fetch options
  if (fetchArgs.length !== 2 || typeof fetchArgs[1] !== 'object') {
    return undefined;
  }

  return (fetchArgs[1] ).body;
}

function getAllHeaders(headers, allowedHeaders) {
  const allHeaders = {};

  allowedHeaders.forEach(header => {
    if (headers.get(header)) {
      allHeaders[header] = headers.get(header) ;
    }
  });

  return allHeaders;
}

function getRequestHeaders(fetchArgs, allowedHeaders) {
  if (fetchArgs.length === 1 && typeof fetchArgs[0] !== 'string') {
    return getHeadersFromOptions(fetchArgs[0] , allowedHeaders);
  }

  if (fetchArgs.length === 2) {
    return getHeadersFromOptions(fetchArgs[1] , allowedHeaders);
  }

  return {};
}

function getHeadersFromOptions(
  input,
  allowedHeaders,
) {
  if (!input) {
    return {};
  }

  const headers = input.headers;

  if (!headers) {
    return {};
  }

  if (headers instanceof Headers) {
    return getAllHeaders(headers, allowedHeaders);
  }

  // We do not support this, as it is not really documented (anymore?)
  if (Array.isArray(headers)) {
    return {};
  }

  return getAllowedHeaders(headers, allowedHeaders);
}

function _tryCloneResponse(response) {
  try {
    // We have to clone this, as the body can only be read once
    return response.clone();
  } catch (error) {
    // this can throw if the response was already consumed before
    DEBUG_BUILD && utils.logger.warn('[Replay] Failed to clone response body', error);
  }
}

/**
 * Get the response body of a fetch request, or timeout after 500ms.
 * Fetch can return a streaming body, that may not resolve (or not for a long time).
 * If that happens, we rather abort after a short time than keep waiting for this.
 */
function _tryGetResponseText(response) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Timeout while trying to read response body')), 500);

    _getResponseText(response)
      .then(
        txt => resolve(txt),
        reason => reject(reason),
      )
      .finally(() => clearTimeout(timeout));
  });
}

async function _getResponseText(response) {
  // Force this to be a promise, just to be safe
  // eslint-disable-next-line no-return-await
  return await response.text();
}

/**
 * Capture an XHR breadcrumb to a replay.
 * This adds additional data (where approriate).
 */
async function captureXhrBreadcrumbToReplay(
  breadcrumb,
  hint,
  options,
) {
  try {
    const data = _prepareXhrData(breadcrumb, hint, options);

    // Create a replay performance entry from this breadcrumb
    const result = makeNetworkReplayBreadcrumb('resource.xhr', data);
    addNetworkBreadcrumb(options.replay, result);
  } catch (error) {
    DEBUG_BUILD && utils.logger.error('[Replay] Failed to capture xhr breadcrumb', error);
  }
}

/**
 * Enrich a breadcrumb with additional data.
 * This has to be sync & mutate the given breadcrumb,
 * as the breadcrumb is afterwards consumed by other handlers.
 */
function enrichXhrBreadcrumb(
  breadcrumb,
  hint,
  options,
) {
  const { xhr, input } = hint;

  if (!xhr) {
    return;
  }

  const reqSize = getBodySize(input, options.textEncoder);
  const resSize = xhr.getResponseHeader('content-length')
    ? parseContentLengthHeader(xhr.getResponseHeader('content-length'))
    : _getBodySize(xhr.response, xhr.responseType, options.textEncoder);

  if (reqSize !== undefined) {
    breadcrumb.data.request_body_size = reqSize;
  }
  if (resSize !== undefined) {
    breadcrumb.data.response_body_size = resSize;
  }
}

function _prepareXhrData(
  breadcrumb,
  hint,
  options,
) {
  const now = Date.now();
  const { startTimestamp = now, endTimestamp = now, input, xhr } = hint;

  const {
    url,
    method,
    status_code: statusCode = 0,
    request_body_size: requestBodySize,
    response_body_size: responseBodySize,
  } = breadcrumb.data;

  if (!url) {
    return null;
  }

  if (!xhr || !urlMatches(url, options.networkDetailAllowUrls) || urlMatches(url, options.networkDetailDenyUrls)) {
    const request = buildSkippedNetworkRequestOrResponse(requestBodySize);
    const response = buildSkippedNetworkRequestOrResponse(responseBodySize);
    return {
      startTimestamp,
      endTimestamp,
      url,
      method,
      statusCode,
      request,
      response,
    };
  }

  const xhrInfo = xhr[utils.SENTRY_XHR_DATA_KEY];
  const networkRequestHeaders = xhrInfo
    ? getAllowedHeaders(xhrInfo.request_headers, options.networkRequestHeaders)
    : {};
  const networkResponseHeaders = getAllowedHeaders(getResponseHeaders(xhr), options.networkResponseHeaders);

  const [requestBody, requestWarning] = options.networkCaptureBodies ? getBodyString(input) : [undefined];
  const [responseBody, responseWarning] = options.networkCaptureBodies ? _getXhrResponseBody(xhr) : [undefined];

  const request = buildNetworkRequestOrResponse(networkRequestHeaders, requestBodySize, requestBody);
  const response = buildNetworkRequestOrResponse(networkResponseHeaders, responseBodySize, responseBody);

  return {
    startTimestamp,
    endTimestamp,
    url,
    method,
    statusCode,
    request: requestWarning ? mergeWarning(request, requestWarning) : request,
    response: responseWarning ? mergeWarning(response, responseWarning) : response,
  };
}

function getResponseHeaders(xhr) {
  const headers = xhr.getAllResponseHeaders();

  if (!headers) {
    return {};
  }

  return headers.split('\r\n').reduce((acc, line) => {
    const [key, value] = line.split(': ');
    acc[key.toLowerCase()] = value;
    return acc;
  }, {});
}

function _getXhrResponseBody(xhr) {
  // We collect errors that happen, but only log them if we can't get any response body
  const errors = [];

  try {
    return [xhr.responseText];
  } catch (e) {
    errors.push(e);
  }

  // Try to manually parse the response body, if responseText fails
  try {
    return _parseXhrResponse(xhr.response, xhr.responseType);
  } catch (e) {
    errors.push(e);
  }

  DEBUG_BUILD && utils.logger.warn('[Replay] Failed to get xhr response body', ...errors);

  return [undefined];
}

/**
 * Get the string representation of the XHR response.
 * Based on MDN, these are the possible types of the response:
 * string
 * ArrayBuffer
 * Blob
 * Document
 * POJO
 *
 * Exported only for tests.
 */
function _parseXhrResponse(
  body,
  responseType,
) {
  try {
    if (typeof body === 'string') {
      return [body];
    }

    if (body instanceof Document) {
      return [body.body.outerHTML];
    }

    if (responseType === 'json' && body && typeof body === 'object') {
      return [JSON.stringify(body)];
    }

    if (!body) {
      return [undefined];
    }
  } catch (e2) {
    DEBUG_BUILD && utils.logger.warn('[Replay] Failed to serialize body', body);
    return [undefined, 'BODY_PARSE_ERROR'];
  }

  DEBUG_BUILD && utils.logger.info('[Replay] Skipping network body because of body type', body);

  return [undefined, 'UNPARSEABLE_BODY_TYPE'];
}

function _getBodySize(
  body,
  responseType,
  textEncoder,
) {
  try {
    const bodyStr = responseType === 'json' && body && typeof body === 'object' ? JSON.stringify(body) : body;
    return getBodySize(bodyStr, textEncoder);
  } catch (e3) {
    return undefined;
  }
}

/**
 * This method does two things:
 * - It enriches the regular XHR/fetch breadcrumbs with request/response size data
 * - It captures the XHR/fetch breadcrumbs to the replay
 *   (enriching it with further data that is _not_ added to the regular breadcrumbs)
 */
function handleNetworkBreadcrumbs(replay) {
  const client = core.getClient();

  try {
    const textEncoder = new TextEncoder();

    const {
      networkDetailAllowUrls,
      networkDetailDenyUrls,
      networkCaptureBodies,
      networkRequestHeaders,
      networkResponseHeaders,
    } = replay.getOptions();

    const options = {
      replay,
      textEncoder,
      networkDetailAllowUrls,
      networkDetailDenyUrls,
      networkCaptureBodies,
      networkRequestHeaders,
      networkResponseHeaders,
    };

    if (client && client.on) {
      client.on('beforeAddBreadcrumb', (breadcrumb, hint) => beforeAddNetworkBreadcrumb(options, breadcrumb, hint));
    } else {
      // Fallback behavior
      utils.addFetchInstrumentationHandler(handleFetchSpanListener(replay));
      utils.addXhrInstrumentationHandler(handleXhrSpanListener(replay));
    }
  } catch (e2) {
    // Do nothing
  }
}

/** just exported for tests */
function beforeAddNetworkBreadcrumb(
  options,
  breadcrumb,
  hint,
) {
  if (!breadcrumb.data) {
    return;
  }

  try {
    if (_isXhrBreadcrumb(breadcrumb) && _isXhrHint(hint)) {
      // This has to be sync, as we need to ensure the breadcrumb is enriched in the same tick
      // Because the hook runs synchronously, and the breadcrumb is afterwards passed on
      // So any async mutations to it will not be reflected in the final breadcrumb
      enrichXhrBreadcrumb(breadcrumb, hint, options);

      void captureXhrBreadcrumbToReplay(breadcrumb, hint, options);
    }

    if (_isFetchBreadcrumb(breadcrumb) && _isFetchHint(hint)) {
      // This has to be sync, as we need to ensure the breadcrumb is enriched in the same tick
      // Because the hook runs synchronously, and the breadcrumb is afterwards passed on
      // So any async mutations to it will not be reflected in the final breadcrumb
      enrichFetchBreadcrumb(breadcrumb, hint, options);

      void captureFetchBreadcrumbToReplay(breadcrumb, hint, options);
    }
  } catch (e) {
    DEBUG_BUILD && utils.logger.warn('Error when enriching network breadcrumb');
  }
}

function _isXhrBreadcrumb(breadcrumb) {
  return breadcrumb.category === 'xhr';
}

function _isFetchBreadcrumb(breadcrumb) {
  return breadcrumb.category === 'fetch';
}

function _isXhrHint(hint) {
  return hint && hint.xhr;
}

function _isFetchHint(hint) {
  return hint && hint.response;
}

let _LAST_BREADCRUMB = null;

function isBreadcrumbWithCategory(breadcrumb) {
  return !!breadcrumb.category;
}

const handleScopeListener =
  (replay) =>
  (scope) => {
    if (!replay.isEnabled()) {
      return;
    }

    const result = handleScope(scope);

    if (!result) {
      return;
    }

    addBreadcrumbEvent(replay, result);
  };

/**
 * An event handler to handle scope changes.
 */
function handleScope(scope) {
  // TODO (v8): Remove this guard. This was put in place because we introduced
  // Scope.getLastBreadcrumb mid-v7 which caused incompatibilities with older SDKs.
  // For now, we'll just return null if the method doesn't exist but we should eventually
  // get rid of this guard.
  const newBreadcrumb = scope.getLastBreadcrumb && scope.getLastBreadcrumb();

  // Listener can be called when breadcrumbs have not changed, so we store the
  // reference to the last crumb and only return a crumb if it has changed
  if (_LAST_BREADCRUMB === newBreadcrumb || !newBreadcrumb) {
    return null;
  }

  _LAST_BREADCRUMB = newBreadcrumb;

  if (
    !isBreadcrumbWithCategory(newBreadcrumb) ||
    ['fetch', 'xhr', 'sentry.event', 'sentry.transaction'].includes(newBreadcrumb.category) ||
    newBreadcrumb.category.startsWith('ui.')
  ) {
    return null;
  }

  if (newBreadcrumb.category === 'console') {
    return normalizeConsoleBreadcrumb(newBreadcrumb);
  }

  return createBreadcrumb(newBreadcrumb);
}

/** exported for tests only */
function normalizeConsoleBreadcrumb(
  breadcrumb,
) {
  const args = breadcrumb.data && breadcrumb.data.arguments;

  if (!Array.isArray(args) || args.length === 0) {
    return createBreadcrumb(breadcrumb);
  }

  let isTruncated = false;

  // Avoid giant args captures
  const normalizedArgs = args.map(arg => {
    if (!arg) {
      return arg;
    }
    if (typeof arg === 'string') {
      if (arg.length > CONSOLE_ARG_MAX_SIZE) {
        isTruncated = true;
        return `${arg.slice(0, CONSOLE_ARG_MAX_SIZE)}…`;
      }

      return arg;
    }
    if (typeof arg === 'object') {
      try {
        const normalizedArg = utils.normalize(arg, 7);
        const stringified = JSON.stringify(normalizedArg);
        if (stringified.length > CONSOLE_ARG_MAX_SIZE) {
          isTruncated = true;
          // We use the pretty printed JSON string here as a base
          return `${JSON.stringify(normalizedArg, null, 2).slice(0, CONSOLE_ARG_MAX_SIZE)}…`;
        }
        return normalizedArg;
      } catch (e) {
        // fall back to default
      }
    }

    return arg;
  });

  return createBreadcrumb({
    ...breadcrumb,
    data: {
      ...breadcrumb.data,
      arguments: normalizedArgs,
      ...(isTruncated ? { _meta: { warnings: ['CONSOLE_ARG_TRUNCATED'] } } : {}),
    },
  });
}

/**
 * Add global listeners that cannot be removed.
 */
function addGlobalListeners(replay) {
  // Listeners from core SDK //
  const scope = core.getCurrentHub().getScope();
  const client = core.getClient();

  scope.addScopeListener(handleScopeListener(replay));
  utils.addClickKeypressInstrumentationHandler(handleDomListener(replay));
  utils.addHistoryInstrumentationHandler(handleHistorySpanListener(replay));
  handleNetworkBreadcrumbs(replay);

  // Tag all (non replay) events that get sent to Sentry with the current
  // replay ID so that we can reference them later in the UI
  const eventProcessor = handleGlobalEventListener(replay, !hasHooks(client));
  if (client && client.addEventProcessor) {
    client.addEventProcessor(eventProcessor);
  } else {
    core.addEventProcessor(eventProcessor);
  }

  // If a custom client has no hooks yet, we continue to use the "old" implementation
  if (hasHooks(client)) {
    client.on('afterSendEvent', handleAfterSendEvent(replay));
    client.on('createDsc', (dsc) => {
      const replayId = replay.getSessionId();
      // We do not want to set the DSC when in buffer mode, as that means the replay has not been sent (yet)
      if (replayId && replay.isEnabled() && replay.recordingMode === 'session') {
        // Ensure to check that the session is still active - it could have expired in the meanwhile
        const isSessionActive = replay.checkAndHandleExpiredSession();
        if (isSessionActive) {
          dsc.replay_id = replayId;
        }
      }
    });

    client.on('startTransaction', transaction => {
      replay.lastTransaction = transaction;
    });

    // We may be missing the initial startTransaction due to timing issues,
    // so we capture it on finish again.
    client.on('finishTransaction', transaction => {
      replay.lastTransaction = transaction;
    });

    // We want to flush replay
    client.on('beforeSendFeedback', (feedbackEvent, options) => {
      const replayId = replay.getSessionId();
      if (options && options.includeReplay && replay.isEnabled() && replayId) {
        void replay.flush();
        if (feedbackEvent.contexts && feedbackEvent.contexts.feedback) {
          feedbackEvent.contexts.feedback.replay_id = replayId;
        }
      }
    });
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function hasHooks(client) {
  return !!(client && client.on);
}

/**
 * Create a "span" for the total amount of memory being used by JS objects
 * (including v8 internal objects).
 */
async function addMemoryEntry(replay) {
  // window.performance.memory is a non-standard API and doesn't work on all browsers, so we try-catch this
  try {
    return Promise.all(
      createPerformanceSpans(replay, [
        // @ts-expect-error memory doesn't exist on type Performance as the API is non-standard (we check that it exists above)
        createMemoryEntry(WINDOW.performance.memory),
      ]),
    );
  } catch (error) {
    // Do nothing
    return [];
  }
}

function createMemoryEntry(memoryEntry) {
  const { jsHeapSizeLimit, totalJSHeapSize, usedJSHeapSize } = memoryEntry;
  // we don't want to use `getAbsoluteTime` because it adds the event time to the
  // time origin, so we get the current timestamp instead
  const time = Date.now() / 1000;
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

/**
 * Heavily simplified debounce function based on lodash.debounce.
 *
 * This function takes a callback function (@param fun) and delays its invocation
 * by @param wait milliseconds. Optionally, a maxWait can be specified in @param options,
 * which ensures that the callback is invoked at least once after the specified max. wait time.
 *
 * @param func the function whose invocation is to be debounced
 * @param wait the minimum time until the function is invoked after it was called once
 * @param options the options object, which can contain the `maxWait` property
 *
 * @returns the debounced version of the function, which needs to be called at least once to start the
 *          debouncing process. Subsequent calls will reset the debouncing timer and, in case @paramfunc
 *          was already invoked in the meantime, return @param func's return value.
 *          The debounced function has two additional properties:
 *          - `flush`: Invokes the debounced function immediately and returns its return value
 *          - `cancel`: Cancels the debouncing process and resets the debouncing timer
 */
function debounce(func, wait, options) {
  let callbackReturnValue;

  let timerId;
  let maxTimerId;

  const maxWait = options && options.maxWait ? Math.max(options.maxWait, wait) : 0;

  function invokeFunc() {
    cancelTimers();
    callbackReturnValue = func();
    return callbackReturnValue;
  }

  function cancelTimers() {
    timerId !== undefined && clearTimeout(timerId);
    maxTimerId !== undefined && clearTimeout(maxTimerId);
    timerId = maxTimerId = undefined;
  }

  function flush() {
    if (timerId !== undefined || maxTimerId !== undefined) {
      return invokeFunc();
    }
    return callbackReturnValue;
  }

  function debounced() {
    if (timerId) {
      clearTimeout(timerId);
    }
    timerId = setTimeout(invokeFunc, wait);

    if (maxWait && maxTimerId === undefined) {
      maxTimerId = setTimeout(invokeFunc, maxWait);
    }

    return callbackReturnValue;
  }

  debounced.cancel = cancelTimers;
  debounced.flush = flush;
  return debounced;
}

/**
 * Handler for recording events.
 *
 * Adds to event buffer, and has varying flushing behaviors if the event was a checkout.
 */
function getHandleRecordingEmit(replay) {
  let hadFirstEvent = false;

  return (event, _isCheckout) => {
    // If this is false, it means session is expired, create and a new session and wait for checkout
    if (!replay.checkAndHandleExpiredSession()) {
      DEBUG_BUILD && utils.logger.warn('[Replay] Received replay event after session expired.');

      return;
    }

    // `_isCheckout` is only set when the checkout is due to `checkoutEveryNms`
    // We also want to treat the first event as a checkout, so we handle this specifically here
    const isCheckout = _isCheckout || !hadFirstEvent;
    hadFirstEvent = true;

    if (replay.clickDetector) {
      updateClickDetectorForRecordingEvent(replay.clickDetector, event);
    }

    // The handler returns `true` if we do not want to trigger debounced flush, `false` if we want to debounce flush.
    replay.addUpdate(() => {
      // The session is always started immediately on pageload/init, but for
      // error-only replays, it should reflect the most recent checkout
      // when an error occurs. Clear any state that happens before this current
      // checkout. This needs to happen before `addEvent()` which updates state
      // dependent on this reset.
      if (replay.recordingMode === 'buffer' && isCheckout) {
        replay.setInitialState();
      }

      // If the event is not added (e.g. due to being paused, disabled, or out of the max replay duration),
      // Skip all further steps
      if (!addEventSync(replay, event, isCheckout)) {
        // Return true to skip scheduling a debounced flush
        return true;
      }

      // Different behavior for full snapshots (type=2), ignore other event types
      // See https://github.com/rrweb-io/rrweb/blob/d8f9290ca496712aa1e7d472549480c4e7876594/packages/rrweb/src/types.ts#L16
      if (!isCheckout) {
        return false;
      }

      // Additionally, create a meta event that will capture certain SDK settings.
      // In order to handle buffer mode, this needs to either be done when we
      // receive checkout events or at flush time.
      //
      // `isCheckout` is always true, but want to be explicit that it should
      // only be added for checkouts
      addSettingsEvent(replay, isCheckout);

      // If there is a previousSessionId after a full snapshot occurs, then
      // the replay session was started due to session expiration. The new session
      // is started before triggering a new checkout and contains the id
      // of the previous session. Do not immediately flush in this case
      // to avoid capturing only the checkout and instead the replay will
      // be captured if they perform any follow-up actions.
      if (replay.session && replay.session.previousSessionId) {
        return true;
      }

      // When in buffer mode, make sure we adjust the session started date to the current earliest event of the buffer
      // this should usually be the timestamp of the checkout event, but to be safe...
      if (replay.recordingMode === 'buffer' && replay.session && replay.eventBuffer) {
        const earliestEvent = replay.eventBuffer.getEarliestTimestamp();
        if (earliestEvent) {
          logInfo(
            `[Replay] Updating session start time to earliest event in buffer to ${new Date(earliestEvent)}`,
            replay.getOptions()._experiments.traceInternals,
          );

          replay.session.started = earliestEvent;

          if (replay.getOptions().stickySession) {
            saveSession(replay.session);
          }
        }
      }

      if (replay.recordingMode === 'session') {
        // If the full snapshot is due to an initial load, we will not have
        // a previous session ID. In this case, we want to buffer events
        // for a set amount of time before flushing. This can help avoid
        // capturing replays of users that immediately close the window.
        void replay.flush();
      }

      return true;
    });
  };
}

/**
 * Exported for tests
 */
function createOptionsEvent(replay) {
  const options = replay.getOptions();
  return {
    type: EventType.Custom,
    timestamp: Date.now(),
    data: {
      tag: 'options',
      payload: {
        sessionSampleRate: options.sessionSampleRate,
        errorSampleRate: options.errorSampleRate,
        useCompressionOption: options.useCompression,
        blockAllMedia: options.blockAllMedia,
        maskAllText: options.maskAllText,
        maskAllInputs: options.maskAllInputs,
        useCompression: replay.eventBuffer ? replay.eventBuffer.type === 'worker' : false,
        networkDetailHasUrls: options.networkDetailAllowUrls.length > 0,
        networkCaptureBodies: options.networkCaptureBodies,
        networkRequestHasHeaders: options.networkRequestHeaders.length > 0,
        networkResponseHasHeaders: options.networkResponseHeaders.length > 0,
      },
    },
  };
}

/**
 * Add a "meta" event that contains a simplified view on current configuration
 * options. This should only be included on the first segment of a recording.
 */
function addSettingsEvent(replay, isCheckout) {
  // Only need to add this event when sending the first segment
  if (!isCheckout || !replay.session || replay.session.segmentId !== 0) {
    return;
  }

  addEventSync(replay, createOptionsEvent(replay), false);
}

/**
 * Create a replay envelope ready to be sent.
 * This includes both the replay event, as well as the recording data.
 */
function createReplayEnvelope(
  replayEvent,
  recordingData,
  dsn,
  tunnel,
) {
  return utils.createEnvelope(
    utils.createEventEnvelopeHeaders(replayEvent, utils.getSdkMetadataForEnvelopeHeader(replayEvent), tunnel, dsn),
    [
      [{ type: 'replay_event' }, replayEvent],
      [
        {
          type: 'replay_recording',
          // If string then we need to encode to UTF8, otherwise will have
          // wrong size. TextEncoder has similar browser support to
          // MutationObserver, although it does not accept IE11.
          length:
            typeof recordingData === 'string' ? new TextEncoder().encode(recordingData).length : recordingData.length,
        },
        recordingData,
      ],
    ],
  );
}

/**
 * Prepare the recording data ready to be sent.
 */
function prepareRecordingData({
  recordingData,
  headers,
}

) {
  let payloadWithSequence;

  // XXX: newline is needed to separate sequence id from events
  const replayHeaders = `${JSON.stringify(headers)}
`;

  if (typeof recordingData === 'string') {
    payloadWithSequence = `${replayHeaders}${recordingData}`;
  } else {
    const enc = new TextEncoder();
    // XXX: newline is needed to separate sequence id from events
    const sequence = enc.encode(replayHeaders);
    // Merge the two Uint8Arrays
    payloadWithSequence = new Uint8Array(sequence.length + recordingData.length);
    payloadWithSequence.set(sequence);
    payloadWithSequence.set(recordingData, sequence.length);
  }

  return payloadWithSequence;
}

/**
 * Prepare a replay event & enrich it with the SDK metadata.
 */
async function prepareReplayEvent({
  client,
  scope,
  replayId: event_id,
  event,
}

) {
  const integrations =
    typeof client._integrations === 'object' && client._integrations !== null && !Array.isArray(client._integrations)
      ? Object.keys(client._integrations)
      : undefined;

  const eventHint = { event_id, integrations };

  if (client.emit) {
    client.emit('preprocessEvent', event, eventHint);
  }

  const preparedEvent = (await core.prepareEvent(
    client.getOptions(),
    event,
    eventHint,
    scope,
    client,
  )) ;

  // If e.g. a global event processor returned null
  if (!preparedEvent) {
    return null;
  }

  // This normally happens in browser client "_prepareEvent"
  // but since we do not use this private method from the client, but rather the plain import
  // we need to do this manually.
  preparedEvent.platform = preparedEvent.platform || 'javascript';

  // extract the SDK name because `client._prepareEvent` doesn't add it to the event
  const metadata = client.getSdkMetadata && client.getSdkMetadata();
  const { name, version } = (metadata && metadata.sdk) || {};

  preparedEvent.sdk = {
    ...preparedEvent.sdk,
    name: name || 'sentry.javascript.unknown',
    version: version || '0.0.0',
  };

  return preparedEvent;
}

/**
 * Send replay attachment using `fetch()`
 */
async function sendReplayRequest({
  recordingData,
  replayId,
  segmentId: segment_id,
  eventContext,
  timestamp,
  session,
}) {
  const preparedRecordingData = prepareRecordingData({
    recordingData,
    headers: {
      segment_id,
    },
  });

  const { urls, errorIds, traceIds, initialTimestamp } = eventContext;

  const hub = core.getCurrentHub();
  const client = hub.getClient();
  const scope = hub.getScope();
  const transport = client && client.getTransport();
  const dsn = client && client.getDsn();

  if (!client || !transport || !dsn || !session.sampled) {
    return;
  }

  const baseEvent = {
    type: REPLAY_EVENT_NAME,
    replay_start_timestamp: initialTimestamp / 1000,
    timestamp: timestamp / 1000,
    error_ids: errorIds,
    trace_ids: traceIds,
    urls,
    replay_id: replayId,
    segment_id,
    replay_type: session.sampled,
  };

  const replayEvent = await prepareReplayEvent({ scope, client, replayId, event: baseEvent });

  if (!replayEvent) {
    // Taken from baseclient's `_processEvent` method, where this is handled for errors/transactions
    client.recordDroppedEvent('event_processor', 'replay', baseEvent);
    logInfo('An event processor returned `null`, will not send event.');
    return;
  }

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
      "replay_type": "error",
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
      "contexts": {
      },
  }
  */

  // Prevent this data (which, if it exists, was used in earlier steps in the processing pipeline) from being sent to
  // sentry. (Note: Our use of this property comes and goes with whatever we might be debugging, whatever hacks we may
  // have temporarily added, etc. Even if we don't happen to be using it at some point in the future, let's not get rid
  // of this `delete`, lest we miss putting it back in the next time the property is in use.)
  delete replayEvent.sdkProcessingMetadata;

  const envelope = createReplayEnvelope(replayEvent, preparedRecordingData, dsn, client.getOptions().tunnel);

  let response;

  try {
    response = await transport.send(envelope);
  } catch (err) {
    const error = new Error(UNABLE_TO_SEND_REPLAY);

    try {
      // In case browsers don't allow this property to be writable
      // @ts-expect-error This needs lib es2022 and newer
      error.cause = err;
    } catch (e) {
      // nothing to do
    }
    throw error;
  }

  // TODO (v8): we can remove this guard once transport.send's type signature doesn't include void anymore
  if (!response) {
    return response;
  }

  // If the status code is invalid, we want to immediately stop & not retry
  if (typeof response.statusCode === 'number' && (response.statusCode < 200 || response.statusCode >= 300)) {
    throw new TransportStatusCodeError(response.statusCode);
  }

  const rateLimits = utils.updateRateLimits({}, response);
  if (utils.isRateLimited(rateLimits, 'replay')) {
    throw new RateLimitError(rateLimits);
  }

  return response;
}

/**
 * This error indicates that the transport returned an invalid status code.
 */
class TransportStatusCodeError extends Error {
   constructor(statusCode) {
    super(`Transport returned status code ${statusCode}`);
  }
}

/**
 * This error indicates that we hit a rate limit API error.
 */
class RateLimitError extends Error {

   constructor(rateLimits) {
    super('Rate limit hit');
    this.rateLimits = rateLimits;
  }
}

/**
 * Finalize and send the current replay event to Sentry
 */
async function sendReplay(
  replayData,
  retryConfig = {
    count: 0,
    interval: RETRY_BASE_INTERVAL,
  },
) {
  const { recordingData, options } = replayData;

  // short circuit if there's no events to upload (this shouldn't happen as _runFlush makes this check)
  if (!recordingData.length) {
    return;
  }

  try {
    await sendReplayRequest(replayData);
    return true;
  } catch (err) {
    if (err instanceof TransportStatusCodeError || err instanceof RateLimitError) {
      throw err;
    }

    // Capture error for every failed replay
    core.setContext('Replays', {
      _retryCount: retryConfig.count,
    });

    if (DEBUG_BUILD && options._experiments && options._experiments.captureExceptions) {
      core.captureException(err);
    }

    // If an error happened here, it's likely that uploading the attachment
    // failed, we'll can retry with the same events payload
    if (retryConfig.count >= RETRY_MAX_COUNT) {
      const error = new Error(`${UNABLE_TO_SEND_REPLAY} - max retries exceeded`);

      try {
        // In case browsers don't allow this property to be writable
        // @ts-expect-error This needs lib es2022 and newer
        error.cause = err;
      } catch (e) {
        // nothing to do
      }

      throw error;
    }

    // will retry in intervals of 5, 10, 30
    retryConfig.interval *= ++retryConfig.count;

    return new Promise((resolve, reject) => {
      setTimeout(async () => {
        try {
          await sendReplay(replayData, retryConfig);
          resolve(true);
        } catch (err) {
          reject(err);
        }
      }, retryConfig.interval);
    });
  }
}

const THROTTLED = '__THROTTLED';
const SKIPPED = '__SKIPPED';

/**
 * Create a throttled function off a given function.
 * When calling the throttled function, it will call the original function only
 * if it hasn't been called more than `maxCount` times in the last `durationSeconds`.
 *
 * Returns `THROTTLED` if throttled for the first time, after that `SKIPPED`,
 * or else the return value of the original function.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function throttle(
  fn,
  maxCount,
  durationSeconds,
) {
  const counter = new Map();

  const _cleanup = (now) => {
    const threshold = now - durationSeconds;
    counter.forEach((_value, key) => {
      if (key < threshold) {
        counter.delete(key);
      }
    });
  };

  const _getTotalCount = () => {
    return [...counter.values()].reduce((a, b) => a + b, 0);
  };

  let isThrottled = false;

  return (...rest) => {
    // Date in second-precision, which we use as basis for the throttling
    const now = Math.floor(Date.now() / 1000);

    // First, make sure to delete any old entries
    _cleanup(now);

    // If already over limit, do nothing
    if (_getTotalCount() >= maxCount) {
      const wasThrottled = isThrottled;
      isThrottled = true;
      return wasThrottled ? SKIPPED : THROTTLED;
    }

    isThrottled = false;
    const count = counter.get(now) || 0;
    counter.set(now, count + 1);

    return fn(...rest);
  };
}

/* eslint-disable max-lines */ // TODO: We might want to split this file up

/**
 * The main replay container class, which holds all the state and methods for recording and sending replays.
 */
class ReplayContainer  {

  /**
   * Recording can happen in one of three modes:
   *   - session: Record the whole session, sending it continuously
   *   - buffer: Always keep the last 60s of recording, requires:
   *     - having replaysOnErrorSampleRate > 0 to capture replay when an error occurs
   *     - or calling `flush()` to send the replay
   */

  /**
   * The current or last active transcation.
   * This is only available when performance is enabled.
   */

  /**
   * These are here so we can overwrite them in tests etc.
   * @hidden
   */

  /**
   * Options to pass to `rrweb.record()`
   */

  /**
   * Timestamp of the last user activity. This lives across sessions.
   */

  /**
   * Is the integration currently active?
   */

  /**
   * Paused is a state where:
   * - DOM Recording is not listening at all
   * - Nothing will be added to event buffer (e.g. core SDK events)
   */

  /**
   * Have we attached listeners to the core SDK?
   * Note we have to track this as there is no way to remove instrumentation handlers.
   */

  /**
   * Function to stop recording
   */

   constructor({
    options,
    recordingOptions,
  }

) {ReplayContainer.prototype.__init.call(this);ReplayContainer.prototype.__init2.call(this);ReplayContainer.prototype.__init3.call(this);ReplayContainer.prototype.__init4.call(this);ReplayContainer.prototype.__init5.call(this);ReplayContainer.prototype.__init6.call(this);
    this.eventBuffer = null;
    this.performanceEntries = [];
    this.replayPerformanceEntries = [];
    this.recordingMode = 'session';
    this.timeouts = {
      sessionIdlePause: SESSION_IDLE_PAUSE_DURATION,
      sessionIdleExpire: SESSION_IDLE_EXPIRE_DURATION,
    } ;
    this._lastActivity = Date.now();
    this._isEnabled = false;
    this._isPaused = false;
    this._hasInitializedCoreListeners = false;
    this._context = {
      errorIds: new Set(),
      traceIds: new Set(),
      urls: [],
      initialTimestamp: Date.now(),
      initialUrl: '',
    };

    this._recordingOptions = recordingOptions;
    this._options = options;

    this._debouncedFlush = debounce(() => this._flush(), this._options.flushMinDelay, {
      maxWait: this._options.flushMaxDelay,
    });

    this._throttledAddEvent = throttle(
      (event, isCheckout) => addEvent(this, event, isCheckout),
      // Max 300 events...
      300,
      // ... per 5s
      5,
    );

    const { slowClickTimeout, slowClickIgnoreSelectors } = this.getOptions();

    const slowClickConfig = slowClickTimeout
      ? {
          threshold: Math.min(SLOW_CLICK_THRESHOLD, slowClickTimeout),
          timeout: slowClickTimeout,
          scrollTimeout: SLOW_CLICK_SCROLL_TIMEOUT,
          ignoreSelector: slowClickIgnoreSelectors ? slowClickIgnoreSelectors.join(',') : '',
        }
      : undefined;

    if (slowClickConfig) {
      this.clickDetector = new ClickDetector(this, slowClickConfig);
    }
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
   * Initializes the plugin based on sampling configuration. Should not be
   * called outside of constructor.
   */
   initializeSampling(previousSessionId) {
    const { errorSampleRate, sessionSampleRate } = this._options;

    // If neither sample rate is > 0, then do nothing - user will need to call one of
    // `start()` or `startBuffering` themselves.
    if (errorSampleRate <= 0 && sessionSampleRate <= 0) {
      return;
    }

    // Otherwise if there is _any_ sample rate set, try to load an existing
    // session, or create a new one.
    this._initializeSessionForSampling(previousSessionId);

    if (!this.session) {
      // This should not happen, something wrong has occurred
      this._handleException(new Error('Unable to initialize and create session'));
      return;
    }

    if (this.session.sampled === false) {
      // This should only occur if `errorSampleRate` is 0 and was unsampled for
      // session-based replay. In this case there is nothing to do.
      return;
    }

    // If segmentId > 0, it means we've previously already captured this session
    // In this case, we still want to continue in `session` recording mode
    this.recordingMode = this.session.sampled === 'buffer' && this.session.segmentId === 0 ? 'buffer' : 'session';

    logInfoNextTick(
      `[Replay] Starting replay in ${this.recordingMode} mode`,
      this._options._experiments.traceInternals,
    );

    this._initializeRecording();
  }

  /**
   * Start a replay regardless of sampling rate. Calling this will always
   * create a new session. Will throw an error if replay is already in progress.
   *
   * Creates or loads a session, attaches listeners to varying events (DOM,
   * _performanceObserver, Recording, Sentry SDK, etc)
   */
   start() {
    if (this._isEnabled && this.recordingMode === 'session') {
      throw new Error('Replay recording is already in progress');
    }

    if (this._isEnabled && this.recordingMode === 'buffer') {
      throw new Error('Replay buffering is in progress, call `flush()` to save the replay');
    }

    logInfoNextTick('[Replay] Starting replay in session mode', this._options._experiments.traceInternals);

    const session = loadOrCreateSession(
      {
        maxReplayDuration: this._options.maxReplayDuration,
        sessionIdleExpire: this.timeouts.sessionIdleExpire,
        traceInternals: this._options._experiments.traceInternals,
      },
      {
        stickySession: this._options.stickySession,
        // This is intentional: create a new session-based replay when calling `start()`
        sessionSampleRate: 1,
        allowBuffering: false,
      },
    );

    this.session = session;

    this._initializeRecording();
  }

  /**
   * Start replay buffering. Buffers until `flush()` is called or, if
   * `replaysOnErrorSampleRate` > 0, an error occurs.
   */
   startBuffering() {
    if (this._isEnabled) {
      throw new Error('Replay recording is already in progress');
    }

    logInfoNextTick('[Replay] Starting replay in buffer mode', this._options._experiments.traceInternals);

    const session = loadOrCreateSession(
      {
        sessionIdleExpire: this.timeouts.sessionIdleExpire,
        maxReplayDuration: this._options.maxReplayDuration,
        traceInternals: this._options._experiments.traceInternals,
      },
      {
        stickySession: this._options.stickySession,
        sessionSampleRate: 0,
        allowBuffering: true,
      },
    );

    this.session = session;

    this.recordingMode = 'buffer';
    this._initializeRecording();
  }

  /**
   * Start recording.
   *
   * Note that this will cause a new DOM checkout
   */
   startRecording() {
    try {
      this._stopRecording = record({
        ...this._recordingOptions,
        // When running in error sampling mode, we need to overwrite `checkoutEveryNms`
        // Without this, it would record forever, until an error happens, which we don't want
        // instead, we'll always keep the last 60 seconds of replay before an error happened
        ...(this.recordingMode === 'buffer' && { checkoutEveryNms: BUFFER_CHECKOUT_TIME }),
        emit: getHandleRecordingEmit(this),
        onMutation: this._onMutationHandler,
      });
    } catch (err) {
      this._handleException(err);
    }
  }

  /**
   * Stops the recording, if it was running.
   *
   * Returns true if it was previously stopped, or is now stopped,
   * otherwise false.
   */
   stopRecording() {
    try {
      if (this._stopRecording) {
        this._stopRecording();
        this._stopRecording = undefined;
      }

      return true;
    } catch (err) {
      this._handleException(err);
      return false;
    }
  }

  /**
   * Currently, this needs to be manually called (e.g. for tests). Sentry SDK
   * does not support a teardown
   */
   async stop({ forceFlush = false, reason } = {}) {
    if (!this._isEnabled) {
      return;
    }

    // We can't move `_isEnabled` after awaiting a flush, otherwise we can
    // enter into an infinite loop when `stop()` is called while flushing.
    this._isEnabled = false;

    try {
      logInfo(
        `[Replay] Stopping Replay${reason ? ` triggered by ${reason}` : ''}`,
        this._options._experiments.traceInternals,
      );

      this._removeListeners();
      this.stopRecording();

      this._debouncedFlush.cancel();
      // See comment above re: `_isEnabled`, we "force" a flush, ignoring the
      // `_isEnabled` state of the plugin since it was disabled above.
      if (forceFlush) {
        await this._flush({ force: true });
      }

      // After flush, destroy event buffer
      this.eventBuffer && this.eventBuffer.destroy();
      this.eventBuffer = null;

      // Clear session from session storage, note this means if a new session
      // is started after, it will not have `previousSessionId`
      clearSession(this);
    } catch (err) {
      this._handleException(err);
    }
  }

  /**
   * Pause some replay functionality. See comments for `_isPaused`.
   * This differs from stop as this only stops DOM recording, it is
   * not as thorough of a shutdown as `stop()`.
   */
   pause() {
    if (this._isPaused) {
      return;
    }

    this._isPaused = true;
    this.stopRecording();

    logInfo('[Replay] Pausing replay', this._options._experiments.traceInternals);
  }

  /**
   * Resumes recording, see notes for `pause().
   *
   * Note that calling `startRecording()` here will cause a
   * new DOM checkout.`
   */
   resume() {
    if (!this._isPaused || !this._checkSession()) {
      return;
    }

    this._isPaused = false;
    this.startRecording();

    logInfo('[Replay] Resuming replay', this._options._experiments.traceInternals);
  }

  /**
   * If not in "session" recording mode, flush event buffer which will create a new replay.
   * Unless `continueRecording` is false, the replay will continue to record and
   * behave as a "session"-based replay.
   *
   * Otherwise, queue up a flush.
   */
   async sendBufferedReplayOrFlush({ continueRecording = true } = {}) {
    if (this.recordingMode === 'session') {
      return this.flushImmediate();
    }

    const activityTime = Date.now();

    logInfo('[Replay] Converting buffer to session', this._options._experiments.traceInternals);

    // Allow flush to complete before resuming as a session recording, otherwise
    // the checkout from `startRecording` may be included in the payload.
    // Prefer to keep the error replay as a separate (and smaller) segment
    // than the session replay.
    await this.flushImmediate();

    const hasStoppedRecording = this.stopRecording();

    if (!continueRecording || !hasStoppedRecording) {
      return;
    }

    // To avoid race conditions where this is called multiple times, we check here again that we are still buffering
    if ((this.recordingMode ) === 'session') {
      return;
    }

    // Re-start recording in session-mode
    this.recordingMode = 'session';

    // Once this session ends, we do not want to refresh it
    if (this.session) {
      this._updateUserActivity(activityTime);
      this._updateSessionActivity(activityTime);
      this._maybeSaveSession();
    }

    this.startRecording();
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
    // We need to always run `cb` (e.g. in the case of `this.recordingMode == 'buffer'`)
    const cbResult = cb();

    // If this option is turned on then we will only want to call `flush`
    // explicitly
    if (this.recordingMode === 'buffer') {
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
   * Updates the user activity timestamp and resumes recording. This should be
   * called in an event handler for a user action that we consider as the user
   * being "active" (e.g. a mouse click).
   */
   triggerUserActivity() {
    this._updateUserActivity();

    // This case means that recording was once stopped due to inactivity.
    // Ensure that recording is resumed.
    if (!this._stopRecording) {
      // Create a new session, otherwise when the user action is flushed, it
      // will get rejected due to an expired session.
      if (!this._checkSession()) {
        return;
      }

      // Note: This will cause a new DOM checkout
      this.resume();
      return;
    }

    // Otherwise... recording was never suspended, continue as normalish
    this.checkAndHandleExpiredSession();

    this._updateSessionActivity();
  }

  /**
   * Updates the user activity timestamp *without* resuming
   * recording. Some user events (e.g. keydown) can be create
   * low-value replays that only contain the keypress as a
   * breadcrumb. Instead this would require other events to
   * create a new replay after a session has expired.
   */
   updateUserActivity() {
    this._updateUserActivity();
    this._updateSessionActivity();
  }

  /**
   * Only flush if `this.recordingMode === 'session'`
   */
   conditionalFlush() {
    if (this.recordingMode === 'buffer') {
      return Promise.resolve();
    }

    return this.flushImmediate();
  }

  /**
   * Flush using debounce flush
   */
   flush() {
    return this._debouncedFlush() ;
  }

  /**
   * Always flush via `_debouncedFlush` so that we do not have flushes triggered
   * from calling both `flush` and `_debouncedFlush`. Otherwise, there could be
   * cases of mulitple flushes happening closely together.
   */
   flushImmediate() {
    this._debouncedFlush();
    // `.flush` is provided by the debounced function, analogously to lodash.debounce
    return this._debouncedFlush.flush() ;
  }

  /**
   * Cancels queued up flushes.
   */
   cancelFlush() {
    this._debouncedFlush.cancel();
  }

  /** Get the current sesion (=replay) ID */
   getSessionId() {
    return this.session && this.session.id;
  }

  /**
   * Checks if recording should be stopped due to user inactivity. Otherwise
   * check if session is expired and create a new session if so. Triggers a new
   * full snapshot on new session.
   *
   * Returns true if session is not expired, false otherwise.
   * @hidden
   */
   checkAndHandleExpiredSession() {
    // Prevent starting a new session if the last user activity is older than
    // SESSION_IDLE_PAUSE_DURATION. Otherwise non-user activity can trigger a new
    // session+recording. This creates noisy replays that do not have much
    // content in them.
    if (
      this._lastActivity &&
      isExpired(this._lastActivity, this.timeouts.sessionIdlePause) &&
      this.session &&
      this.session.sampled === 'session'
    ) {
      // Pause recording only for session-based replays. Otherwise, resuming
      // will create a new replay and will conflict with users who only choose
      // to record error-based replays only. (e.g. the resumed replay will not
      // contain a reference to an error)
      this.pause();
      return;
    }

    // --- There is recent user activity --- //
    // This will create a new session if expired, based on expiry length
    if (!this._checkSession()) {
      // Check session handles the refreshing itself
      return false;
    }

    return true;
  }

  /**
   * Capture some initial state that can change throughout the lifespan of the
   * replay. This is required because otherwise they would be captured at the
   * first flush.
   */
   setInitialState() {
    const urlPath = `${WINDOW.location.pathname}${WINDOW.location.hash}${WINDOW.location.search}`;
    const url = `${WINDOW.location.origin}${urlPath}`;

    this.performanceEntries = [];
    this.replayPerformanceEntries = [];

    // Reset _context as well
    this._clearContext();

    this._context.initialUrl = url;
    this._context.initialTimestamp = Date.now();
    this._context.urls.push(url);
  }

  /**
   * Add a breadcrumb event, that may be throttled.
   * If it was throttled, we add a custom breadcrumb to indicate that.
   */
   throttledAddEvent(
    event,
    isCheckout,
  ) {
    const res = this._throttledAddEvent(event, isCheckout);

    // If this is THROTTLED, it means we have throttled the event for the first time
    // In this case, we want to add a breadcrumb indicating that something was skipped
    if (res === THROTTLED) {
      const breadcrumb = createBreadcrumb({
        category: 'replay.throttled',
      });

      this.addUpdate(() => {
        // Return `false` if the event _was_ added, as that means we schedule a flush
        return !addEventSync(this, {
          type: ReplayEventTypeCustom,
          timestamp: breadcrumb.timestamp || 0,
          data: {
            tag: 'breadcrumb',
            payload: breadcrumb,
            metric: true,
          },
        });
      });
    }

    return res;
  }

  /**
   * This will get the parametrized route name of the current page.
   * This is only available if performance is enabled, and if an instrumented router is used.
   */
   getCurrentRoute() {
    const lastTransaction = this.lastTransaction || core.getCurrentHub().getScope().getTransaction();
    if (!lastTransaction || !['route', 'custom'].includes(lastTransaction.metadata.source)) {
      return undefined;
    }

    return lastTransaction.name;
  }

  /**
   * Initialize and start all listeners to varying events (DOM,
   * Performance Observer, Recording, Sentry SDK, etc)
   */
   _initializeRecording() {
    this.setInitialState();

    // this method is generally called on page load or manually - in both cases
    // we should treat it as an activity
    this._updateSessionActivity();

    this.eventBuffer = createEventBuffer({
      useCompression: this._options.useCompression,
      workerUrl: this._options.workerUrl,
    });

    this._removeListeners();
    this._addListeners();

    // Need to set as enabled before we start recording, as `record()` can trigger a flush with a new checkout
    this._isEnabled = true;
    this._isPaused = false;

    this.startRecording();
  }

  /** A wrapper to conditionally capture exceptions. */
   _handleException(error) {
    DEBUG_BUILD && utils.logger.error('[Replay]', error);

    if (DEBUG_BUILD && this._options._experiments && this._options._experiments.captureExceptions) {
      core.captureException(error);
    }
  }

  /**
   * Loads (or refreshes) the current session.
   */
   _initializeSessionForSampling(previousSessionId) {
    // Whenever there is _any_ error sample rate, we always allow buffering
    // Because we decide on sampling when an error occurs, we need to buffer at all times if sampling for errors
    const allowBuffering = this._options.errorSampleRate > 0;

    const session = loadOrCreateSession(
      {
        sessionIdleExpire: this.timeouts.sessionIdleExpire,
        maxReplayDuration: this._options.maxReplayDuration,
        traceInternals: this._options._experiments.traceInternals,
        previousSessionId,
      },
      {
        stickySession: this._options.stickySession,
        sessionSampleRate: this._options.sessionSampleRate,
        allowBuffering,
      },
    );

    this.session = session;
  }

  /**
   * Checks and potentially refreshes the current session.
   * Returns false if session is not recorded.
   */
   _checkSession() {
    // If there is no session yet, we do not want to refresh anything
    // This should generally not happen, but to be safe....
    if (!this.session) {
      return false;
    }

    const currentSession = this.session;

    if (
      shouldRefreshSession(currentSession, {
        sessionIdleExpire: this.timeouts.sessionIdleExpire,
        maxReplayDuration: this._options.maxReplayDuration,
      })
    ) {
      void this._refreshSession(currentSession);
      return false;
    }

    return true;
  }

  /**
   * Refresh a session with a new one.
   * This stops the current session (without forcing a flush, as that would never work since we are expired),
   * and then does a new sampling based on the refreshed session.
   */
   async _refreshSession(session) {
    if (!this._isEnabled) {
      return;
    }
    await this.stop({ reason: 'refresh session' });
    this.initializeSampling(session.id);
  }

  /**
   * Adds listeners to record events for the replay
   */
   _addListeners() {
    try {
      WINDOW.document.addEventListener('visibilitychange', this._handleVisibilityChange);
      WINDOW.addEventListener('blur', this._handleWindowBlur);
      WINDOW.addEventListener('focus', this._handleWindowFocus);
      WINDOW.addEventListener('keydown', this._handleKeyboardEvent);

      if (this.clickDetector) {
        this.clickDetector.addListeners();
      }

      // There is no way to remove these listeners, so ensure they are only added once
      if (!this._hasInitializedCoreListeners) {
        addGlobalListeners(this);

        this._hasInitializedCoreListeners = true;
      }
    } catch (err) {
      this._handleException(err);
    }

    this._performanceCleanupCallback = setupPerformanceObserver(this);
  }

  /**
   * Cleans up listeners that were created in `_addListeners`
   */
   _removeListeners() {
    try {
      WINDOW.document.removeEventListener('visibilitychange', this._handleVisibilityChange);

      WINDOW.removeEventListener('blur', this._handleWindowBlur);
      WINDOW.removeEventListener('focus', this._handleWindowFocus);
      WINDOW.removeEventListener('keydown', this._handleKeyboardEvent);

      if (this.clickDetector) {
        this.clickDetector.removeListeners();
      }

      if (this._performanceCleanupCallback) {
        this._performanceCleanupCallback();
      }
    } catch (err) {
      this._handleException(err);
    }
  }

  /**
   * Handle when visibility of the page content changes. Opening a new tab will
   * cause the state to change to hidden because of content of current page will
   * be hidden. Likewise, moving a different window to cover the contents of the
   * page will also trigger a change to a hidden state.
   */
   __init() {this._handleVisibilityChange = () => {
    if (WINDOW.document.visibilityState === 'visible') {
      this._doChangeToForegroundTasks();
    } else {
      this._doChangeToBackgroundTasks();
    }
  };}

  /**
   * Handle when page is blurred
   */
   __init2() {this._handleWindowBlur = () => {
    const breadcrumb = createBreadcrumb({
      category: 'ui.blur',
    });

    // Do not count blur as a user action -- it's part of the process of them
    // leaving the page
    this._doChangeToBackgroundTasks(breadcrumb);
  };}

  /**
   * Handle when page is focused
   */
   __init3() {this._handleWindowFocus = () => {
    const breadcrumb = createBreadcrumb({
      category: 'ui.focus',
    });

    // Do not count focus as a user action -- instead wait until they focus and
    // interactive with page
    this._doChangeToForegroundTasks(breadcrumb);
  };}

  /** Ensure page remains active when a key is pressed. */
   __init4() {this._handleKeyboardEvent = (event) => {
    handleKeyboardEvent(this, event);
  };}

  /**
   * Tasks to run when we consider a page to be hidden (via blurring and/or visibility)
   */
   _doChangeToBackgroundTasks(breadcrumb) {
    if (!this.session) {
      return;
    }

    const expired = isSessionExpired(this.session, {
      maxReplayDuration: this._options.maxReplayDuration,
      sessionIdleExpire: this.timeouts.sessionIdleExpire,
    });

    if (expired) {
      return;
    }

    if (breadcrumb) {
      this._createCustomBreadcrumb(breadcrumb);
    }

    // Send replay when the page/tab becomes hidden. There is no reason to send
    // replay if it becomes visible, since no actions we care about were done
    // while it was hidden
    void this.conditionalFlush();
  }

  /**
   * Tasks to run when we consider a page to be visible (via focus and/or visibility)
   */
   _doChangeToForegroundTasks(breadcrumb) {
    if (!this.session) {
      return;
    }

    const isSessionActive = this.checkAndHandleExpiredSession();

    if (!isSessionActive) {
      // If the user has come back to the page within SESSION_IDLE_PAUSE_DURATION
      // ms, we will re-use the existing session, otherwise create a new
      // session
      logInfo('[Replay] Document has become active, but session has expired');
      return;
    }

    if (breadcrumb) {
      this._createCustomBreadcrumb(breadcrumb);
    }
  }

  /**
   * Update user activity (across session lifespans)
   */
   _updateUserActivity(_lastActivity = Date.now()) {
    this._lastActivity = _lastActivity;
  }

  /**
   * Updates the session's last activity timestamp
   */
   _updateSessionActivity(_lastActivity = Date.now()) {
    if (this.session) {
      this.session.lastActivity = _lastActivity;
      this._maybeSaveSession();
    }
  }

  /**
   * Helper to create (and buffer) a replay breadcrumb from a core SDK breadcrumb
   */
   _createCustomBreadcrumb(breadcrumb) {
    this.addUpdate(() => {
      void this.throttledAddEvent({
        type: EventType.Custom,
        timestamp: breadcrumb.timestamp || 0,
        data: {
          tag: 'breadcrumb',
          payload: breadcrumb,
        },
      });
    });
  }

  /**
   * Observed performance events are added to `this.performanceEntries`. These
   * are included in the replay event before it is finished and sent to Sentry.
   */
   _addPerformanceEntries() {
    const performanceEntries = createPerformanceEntries(this.performanceEntries).concat(this.replayPerformanceEntries);

    this.performanceEntries = [];
    this.replayPerformanceEntries = [];

    return Promise.all(createPerformanceSpans(this, performanceEntries));
  }

  /**
   * Clear _context
   */
   _clearContext() {
    // XXX: `initialTimestamp` and `initialUrl` do not get cleared
    this._context.errorIds.clear();
    this._context.traceIds.clear();
    this._context.urls = [];
  }

  /** Update the initial timestamp based on the buffer content. */
   _updateInitialTimestampFromEventBuffer() {
    const { session, eventBuffer } = this;
    if (!session || !eventBuffer) {
      return;
    }

    // we only ever update this on the initial segment
    if (session.segmentId) {
      return;
    }

    const earliestEvent = eventBuffer.getEarliestTimestamp();
    if (earliestEvent && earliestEvent < this._context.initialTimestamp) {
      this._context.initialTimestamp = earliestEvent;
    }
  }

  /**
   * Return and clear _context
   */
   _popEventContext() {
    const _context = {
      initialTimestamp: this._context.initialTimestamp,
      initialUrl: this._context.initialUrl,
      errorIds: Array.from(this._context.errorIds),
      traceIds: Array.from(this._context.traceIds),
      urls: this._context.urls,
    };

    this._clearContext();

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
   async _runFlush() {
    const replayId = this.getSessionId();

    if (!this.session || !this.eventBuffer || !replayId) {
      DEBUG_BUILD && utils.logger.error('[Replay] No session or eventBuffer found to flush.');
      return;
    }

    await this._addPerformanceEntries();

    // Check eventBuffer again, as it could have been stopped in the meanwhile
    if (!this.eventBuffer || !this.eventBuffer.hasEvents) {
      return;
    }

    // Only attach memory event if eventBuffer is not empty
    await addMemoryEntry(this);

    // Check eventBuffer again, as it could have been stopped in the meanwhile
    if (!this.eventBuffer) {
      return;
    }

    // if this changed in the meanwhile, e.g. because the session was refreshed or similar, we abort here
    if (replayId !== this.getSessionId()) {
      return;
    }

    try {
      // This uses the data from the eventBuffer, so we need to call this before `finish()
      this._updateInitialTimestampFromEventBuffer();

      const timestamp = Date.now();

      // Check total duration again, to avoid sending outdated stuff
      // We leave 30s wiggle room to accomodate late flushing etc.
      // This _could_ happen when the browser is suspended during flushing, in which case we just want to stop
      if (timestamp - this._context.initialTimestamp > this._options.maxReplayDuration + 30000) {
        throw new Error('Session is too long, not sending replay');
      }

      const eventContext = this._popEventContext();
      // Always increment segmentId regardless of outcome of sending replay
      const segmentId = this.session.segmentId++;
      this._maybeSaveSession();

      // Note this empties the event buffer regardless of outcome of sending replay
      const recordingData = await this.eventBuffer.finish();

      await sendReplay({
        replayId,
        recordingData,
        segmentId,
        eventContext,
        session: this.session,
        options: this.getOptions(),
        timestamp,
      });
    } catch (err) {
      this._handleException(err);

      // This means we retried 3 times and all of them failed,
      // or we ran into a problem we don't want to retry, like rate limiting.
      // In this case, we want to completely stop the replay - otherwise, we may get inconsistent segments
      void this.stop({ reason: 'sendReplay' });

      const client = core.getClient();

      if (client) {
        client.recordDroppedEvent('send_error', 'replay');
      }
    }
  }

  /**
   * Flush recording data to Sentry. Creates a lock so that only a single flush
   * can be active at a time. Do not call this directly.
   */
   __init5() {this._flush = async ({
    force = false,
  }

 = {}) => {
    if (!this._isEnabled && !force) {
      // This can happen if e.g. the replay was stopped because of exceeding the retry limit
      return;
    }

    if (!this.checkAndHandleExpiredSession()) {
      DEBUG_BUILD && utils.logger.error('[Replay] Attempting to finish replay event after session expired.');
      return;
    }

    if (!this.session) {
      // should never happen, as we would have bailed out before
      return;
    }

    const start = this.session.started;
    const now = Date.now();
    const duration = now - start;

    // A flush is about to happen, cancel any queued flushes
    this._debouncedFlush.cancel();

    // If session is too short, or too long (allow some wiggle room over maxReplayDuration), do not send it
    // This _should_ not happen, but it may happen if flush is triggered due to a page activity change or similar
    const tooShort = duration < this._options.minReplayDuration;
    const tooLong = duration > this._options.maxReplayDuration + 5000;
    if (tooShort || tooLong) {
      logInfo(
        `[Replay] Session duration (${Math.floor(duration / 1000)}s) is too ${
          tooShort ? 'short' : 'long'
        }, not sending replay.`,
        this._options._experiments.traceInternals,
      );

      if (tooShort) {
        this._debouncedFlush();
      }
      return;
    }

    const eventBuffer = this.eventBuffer;
    if (eventBuffer && this.session.segmentId === 0 && !eventBuffer.hasCheckout) {
      logInfo('[Replay] Flushing initial segment without checkout.', this._options._experiments.traceInternals);
      // TODO FN: Evaluate if we want to stop here, or remove this again?
    }

    // this._flushLock acts as a lock so that future calls to `_flush()`
    // will be blocked until this promise resolves
    if (!this._flushLock) {
      this._flushLock = this._runFlush();
      await this._flushLock;
      this._flushLock = undefined;
      return;
    }

    // Wait for previous flush to finish, then call the debounced `_flush()`.
    // It's possible there are other flush requests queued and waiting for it
    // to resolve. We want to reduce all outstanding requests (as well as any
    // new flush requests that occur within a second of the locked flush
    // completing) into a single flush.

    try {
      await this._flushLock;
    } catch (err) {
      DEBUG_BUILD && utils.logger.error(err);
    } finally {
      this._debouncedFlush();
    }
  };}

  /** Save the session, if it is sticky */
   _maybeSaveSession() {
    if (this.session && this._options.stickySession) {
      saveSession(this.session);
    }
  }

  /** Handler for rrweb.record.onMutation */
   __init6() {this._onMutationHandler = (mutations) => {
    const count = mutations.length;

    const mutationLimit = this._options.mutationLimit;
    const mutationBreadcrumbLimit = this._options.mutationBreadcrumbLimit;
    const overMutationLimit = mutationLimit && count > mutationLimit;

    // Create a breadcrumb if a lot of mutations happen at the same time
    // We can show this in the UI as an information with potential performance improvements
    if (count > mutationBreadcrumbLimit || overMutationLimit) {
      const breadcrumb = createBreadcrumb({
        category: 'replay.mutations',
        data: {
          count,
          limit: overMutationLimit,
        },
      });
      this._createCustomBreadcrumb(breadcrumb);
    }

    // Stop replay if over the mutation limit
    if (overMutationLimit) {
      void this.stop({ reason: 'mutationLimit', forceFlush: this.recordingMode === 'session' });
      return false;
    }

    // `true` means we use the regular mutation handling by rrweb
    return true;
  };}
}

function getOption(
  selectors,
  defaultSelectors,
  deprecatedClassOption,
  deprecatedSelectorOption,
) {
  const deprecatedSelectors = typeof deprecatedSelectorOption === 'string' ? deprecatedSelectorOption.split(',') : [];

  const allSelectors = [
    ...selectors,
    // @deprecated
    ...deprecatedSelectors,

    // sentry defaults
    ...defaultSelectors,
  ];

  // @deprecated
  if (typeof deprecatedClassOption !== 'undefined') {
    // NOTE: No support for RegExp
    if (typeof deprecatedClassOption === 'string') {
      allSelectors.push(`.${deprecatedClassOption}`);
    }

    utils.consoleSandbox(() => {
      // eslint-disable-next-line no-console
      console.warn(
        '[Replay] You are using a deprecated configuration item for privacy. Read the documentation on how to use the new privacy configuration.',
      );
    });
  }

  return allSelectors.join(',');
}

/**
 * Returns privacy related configuration for use in rrweb
 */
function getPrivacyOptions({
  mask,
  unmask,
  block,
  unblock,
  ignore,

  // eslint-disable-next-line deprecation/deprecation
  blockClass,
  // eslint-disable-next-line deprecation/deprecation
  blockSelector,
  // eslint-disable-next-line deprecation/deprecation
  maskTextClass,
  // eslint-disable-next-line deprecation/deprecation
  maskTextSelector,
  // eslint-disable-next-line deprecation/deprecation
  ignoreClass,
}) {
  const defaultBlockedElements = ['base[href="/"]'];

  const maskSelector = getOption(mask, ['.sentry-mask', '[data-sentry-mask]'], maskTextClass, maskTextSelector);
  const unmaskSelector = getOption(unmask, ['.sentry-unmask', '[data-sentry-unmask]']);

  const options = {
    // We are making the decision to make text and input selectors the same
    maskTextSelector: maskSelector,
    unmaskTextSelector: unmaskSelector,

    blockSelector: getOption(
      block,
      ['.sentry-block', '[data-sentry-block]', ...defaultBlockedElements],
      blockClass,
      blockSelector,
    ),
    unblockSelector: getOption(unblock, ['.sentry-unblock', '[data-sentry-unblock]']),
    ignoreSelector: getOption(ignore, ['.sentry-ignore', '[data-sentry-ignore]', 'input[type="file"]'], ignoreClass),
  };

  if (blockClass instanceof RegExp) {
    options.blockClass = blockClass;
  }

  if (maskTextClass instanceof RegExp) {
    options.maskTextClass = maskTextClass;
  }

  return options;
}

/**
 * Masks an attribute if necessary, otherwise return attribute value as-is.
 */
function maskAttribute({
  el,
  key,
  maskAttributes,
  maskAllText,
  privacyOptions,
  value,
}) {
  // We only mask attributes if `maskAllText` is true
  if (!maskAllText) {
    return value;
  }

  // unmaskTextSelector takes precendence
  if (privacyOptions.unmaskTextSelector && el.matches(privacyOptions.unmaskTextSelector)) {
    return value;
  }

  if (
    maskAttributes.includes(key) ||
    // Need to mask `value` attribute for `<input>` if it's a button-like
    // type
    (key === 'value' && el.tagName === 'INPUT' && ['submit', 'button'].includes(el.getAttribute('type') || ''))
  ) {
    return value.replace(/[\S]/g, '*');
  }

  return value;
}

const MEDIA_SELECTORS =
  'img,image,svg,video,object,picture,embed,map,audio,link[rel="icon"],link[rel="apple-touch-icon"]';

const DEFAULT_NETWORK_HEADERS = ['content-length', 'content-type', 'accept'];

let _initialized = false;

/**
 * The main replay integration class, to be passed to `init({  integrations: [] })`.
 */
class Replay  {
  /**
   * @inheritDoc
   */
   static __initStatic() {this.id = 'Replay';}

  /**
   * @inheritDoc
   */

  /**
   * Options to pass to `rrweb.record()`
   */

  /**
   * Initial options passed to the replay integration, merged with default values.
   * Note: `sessionSampleRate` and `errorSampleRate` are not required here, as they
   * can only be finally set when setupOnce() is called.
   *
   * @private
   */

   constructor({
    flushMinDelay = DEFAULT_FLUSH_MIN_DELAY,
    flushMaxDelay = DEFAULT_FLUSH_MAX_DELAY,
    minReplayDuration = MIN_REPLAY_DURATION,
    maxReplayDuration = MAX_REPLAY_DURATION,
    stickySession = true,
    useCompression = true,
    workerUrl,
    _experiments = {},
    sessionSampleRate,
    errorSampleRate,
    maskAllText = true,
    maskAllInputs = true,
    blockAllMedia = true,

    mutationBreadcrumbLimit = 750,
    mutationLimit = 10000,

    slowClickTimeout = 7000,
    slowClickIgnoreSelectors = [],

    networkDetailAllowUrls = [],
    networkDetailDenyUrls = [],
    networkCaptureBodies = true,
    networkRequestHeaders = [],
    networkResponseHeaders = [],

    mask = [],
    maskAttributes = ['title', 'placeholder'],
    unmask = [],
    block = [],
    unblock = [],
    ignore = [],
    maskFn,

    beforeAddRecordingEvent,
    beforeErrorSampling,

    // eslint-disable-next-line deprecation/deprecation
    blockClass,
    // eslint-disable-next-line deprecation/deprecation
    blockSelector,
    // eslint-disable-next-line deprecation/deprecation
    maskInputOptions,
    // eslint-disable-next-line deprecation/deprecation
    maskTextClass,
    // eslint-disable-next-line deprecation/deprecation
    maskTextSelector,
    // eslint-disable-next-line deprecation/deprecation
    ignoreClass,
  } = {}) {
    this.name = Replay.id;

    const privacyOptions = getPrivacyOptions({
      mask,
      unmask,
      block,
      unblock,
      ignore,
      blockClass,
      blockSelector,
      maskTextClass,
      maskTextSelector,
      ignoreClass,
    });

    this._recordingOptions = {
      maskAllInputs,
      maskAllText,
      maskInputOptions: { ...(maskInputOptions || {}), password: true },
      maskTextFn: maskFn,
      maskInputFn: maskFn,
      maskAttributeFn: (key, value, el) =>
        maskAttribute({
          maskAttributes,
          maskAllText,
          privacyOptions,
          key,
          value,
          el,
        }),

      ...privacyOptions,

      // Our defaults
      slimDOMOptions: 'all',
      inlineStylesheet: true,
      // Disable inline images as it will increase segment/replay size
      inlineImages: false,
      // collect fonts, but be aware that `sentry.io` needs to be an allowed
      // origin for playback
      collectFonts: true,
      errorHandler: (err) => {
        try {
          err.__rrweb__ = true;
        } catch (error) {
          // ignore errors here
          // this can happen if the error is frozen or does not allow mutation for other reasons
        }
      },
    };

    this._initialOptions = {
      flushMinDelay,
      flushMaxDelay,
      minReplayDuration: Math.min(minReplayDuration, MIN_REPLAY_DURATION_LIMIT),
      maxReplayDuration: Math.min(maxReplayDuration, MAX_REPLAY_DURATION),
      stickySession,
      sessionSampleRate,
      errorSampleRate,
      useCompression,
      workerUrl,
      blockAllMedia,
      maskAllInputs,
      maskAllText,
      mutationBreadcrumbLimit,
      mutationLimit,
      slowClickTimeout,
      slowClickIgnoreSelectors,
      networkDetailAllowUrls,
      networkDetailDenyUrls,
      networkCaptureBodies,
      networkRequestHeaders: _getMergedNetworkHeaders(networkRequestHeaders),
      networkResponseHeaders: _getMergedNetworkHeaders(networkResponseHeaders),
      beforeAddRecordingEvent,
      beforeErrorSampling,

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

      this._initialOptions.sessionSampleRate = sessionSampleRate;
    }

    if (typeof errorSampleRate === 'number') {
      // eslint-disable-next-line
      console.warn(
        `[Replay] You are passing \`errorSampleRate\` to the Replay integration.
This option is deprecated and will be removed soon.
Instead, configure \`replaysOnErrorSampleRate\` directly in the SDK init options, e.g.:
Sentry.init({ replaysOnErrorSampleRate: ${errorSampleRate} })`,
      );

      this._initialOptions.errorSampleRate = errorSampleRate;
    }

    if (this._initialOptions.blockAllMedia) {
      // `blockAllMedia` is a more user friendly option to configure blocking
      // embedded media elements
      this._recordingOptions.blockSelector = !this._recordingOptions.blockSelector
        ? MEDIA_SELECTORS
        : `${this._recordingOptions.blockSelector},${MEDIA_SELECTORS}`;
    }

    if (this._isInitialized && utils.isBrowser()) {
      throw new Error('Multiple Sentry Session Replay instances are not supported');
    }

    this._isInitialized = true;
  }

  /** If replay has already been initialized */
   get _isInitialized() {
    return _initialized;
  }

  /** Update _isInitialized */
   set _isInitialized(value) {
    _initialized = value;
  }

  /**
   * Setup and initialize replay container
   */
   setupOnce() {
    if (!utils.isBrowser()) {
      return;
    }

    this._setup();

    // Once upon a time, we tried to create a transaction in `setupOnce` and it would
    // potentially create a transaction before some native SDK integrations have run
    // and applied their own global event processor. An example is:
    // https://github.com/getsentry/sentry-javascript/blob/b47ceafbdac7f8b99093ce6023726ad4687edc48/packages/browser/src/integrations/useragent.ts
    //
    // So we call `this._initialize()` in next event loop as a workaround to wait for other
    // global event processors to finish. This is no longer needed, but keeping it
    // here to avoid any future issues.
    setTimeout(() => this._initialize());
  }

  /**
   * Start a replay regardless of sampling rate. Calling this will always
   * create a new session. Will throw an error if replay is already in progress.
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
   * Start replay buffering. Buffers until `flush()` is called or, if
   * `replaysOnErrorSampleRate` > 0, until an error occurs.
   */
   startBuffering() {
    if (!this._replay) {
      return;
    }

    this._replay.startBuffering();
  }

  /**
   * Currently, this needs to be manually called (e.g. for tests). Sentry SDK
   * does not support a teardown
   */
   stop() {
    if (!this._replay) {
      return Promise.resolve();
    }

    return this._replay.stop({ forceFlush: this._replay.recordingMode === 'session' });
  }

  /**
   * If not in "session" recording mode, flush event buffer which will create a new replay.
   * Unless `continueRecording` is false, the replay will continue to record and
   * behave as a "session"-based replay.
   *
   * Otherwise, queue up a flush.
   */
   flush(options) {
    if (!this._replay || !this._replay.isEnabled()) {
      return Promise.resolve();
    }

    return this._replay.sendBufferedReplayOrFlush(options);
  }

  /**
   * Get the current session ID.
   */
   getReplayId() {
    if (!this._replay || !this._replay.isEnabled()) {
      return;
    }

    return this._replay.getSessionId();
  }
  /**
   * Initializes replay.
   */
   _initialize() {
    if (!this._replay) {
      return;
    }

    this._replay.initializeSampling();
  }

  /** Setup the integration. */
   _setup() {
    // Client is not available in constructor, so we need to wait until setupOnce
    const finalOptions = loadReplayOptionsFromClient(this._initialOptions);

    this._replay = new ReplayContainer({
      options: finalOptions,
      recordingOptions: this._recordingOptions,
    });
  }
} Replay.__initStatic();

/** Parse Replay-related options from SDK options */
function loadReplayOptionsFromClient(initialOptions) {
  const client = core.getClient();
  const opt = client && (client.getOptions() );

  const finalOptions = { sessionSampleRate: 0, errorSampleRate: 0, ...utils.dropUndefinedKeys(initialOptions) };

  if (!opt) {
    utils.consoleSandbox(() => {
      // eslint-disable-next-line no-console
      console.warn('SDK client is not available.');
    });
    return finalOptions;
  }

  if (
    initialOptions.sessionSampleRate == null && // TODO remove once deprecated rates are removed
    initialOptions.errorSampleRate == null && // TODO remove once deprecated rates are removed
    opt.replaysSessionSampleRate == null &&
    opt.replaysOnErrorSampleRate == null
  ) {
    utils.consoleSandbox(() => {
      // eslint-disable-next-line no-console
      console.warn(
        'Replay is disabled because neither `replaysSessionSampleRate` nor `replaysOnErrorSampleRate` are set.',
      );
    });
  }

  if (typeof opt.replaysSessionSampleRate === 'number') {
    finalOptions.sessionSampleRate = opt.replaysSessionSampleRate;
  }

  if (typeof opt.replaysOnErrorSampleRate === 'number') {
    finalOptions.errorSampleRate = opt.replaysOnErrorSampleRate;
  }

  return finalOptions;
}

function _getMergedNetworkHeaders(headers) {
  return [...DEFAULT_NETWORK_HEADERS, ...headers.map(header => header.toLowerCase())];
}

exports.Replay = Replay;


},{"@sentry-internal/tracing":24,"@sentry/core":65,"@sentry/utils":117}],98:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');
const string = require('./string.js');

/**
 * Creates exceptions inside `event.exception.values` for errors that are nested on properties based on the `key` parameter.
 */
function applyAggregateErrorsToEvent(
  exceptionFromErrorImplementation,
  parser,
  maxValueLimit = 250,
  key,
  limit,
  event,
  hint,
) {
  if (!event.exception || !event.exception.values || !hint || !is.isInstanceOf(hint.originalException, Error)) {
    return;
  }

  // Generally speaking the last item in `event.exception.values` is the exception originating from the original Error
  const originalException =
    event.exception.values.length > 0 ? event.exception.values[event.exception.values.length - 1] : undefined;

  // We only create exception grouping if there is an exception in the event.
  if (originalException) {
    event.exception.values = truncateAggregateExceptions(
      aggregateExceptionsFromError(
        exceptionFromErrorImplementation,
        parser,
        limit,
        hint.originalException ,
        key,
        event.exception.values,
        originalException,
        0,
      ),
      maxValueLimit,
    );
  }
}

function aggregateExceptionsFromError(
  exceptionFromErrorImplementation,
  parser,
  limit,
  error,
  key,
  prevExceptions,
  exception,
  exceptionId,
) {
  if (prevExceptions.length >= limit + 1) {
    return prevExceptions;
  }

  let newExceptions = [...prevExceptions];

  if (is.isInstanceOf(error[key], Error)) {
    applyExceptionGroupFieldsForParentException(exception, exceptionId);
    const newException = exceptionFromErrorImplementation(parser, error[key]);
    const newExceptionId = newExceptions.length;
    applyExceptionGroupFieldsForChildException(newException, key, newExceptionId, exceptionId);
    newExceptions = aggregateExceptionsFromError(
      exceptionFromErrorImplementation,
      parser,
      limit,
      error[key],
      key,
      [newException, ...newExceptions],
      newException,
      newExceptionId,
    );
  }

  // This will create exception grouping for AggregateErrors
  // https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/AggregateError
  if (Array.isArray(error.errors)) {
    error.errors.forEach((childError, i) => {
      if (is.isInstanceOf(childError, Error)) {
        applyExceptionGroupFieldsForParentException(exception, exceptionId);
        const newException = exceptionFromErrorImplementation(parser, childError);
        const newExceptionId = newExceptions.length;
        applyExceptionGroupFieldsForChildException(newException, `errors[${i}]`, newExceptionId, exceptionId);
        newExceptions = aggregateExceptionsFromError(
          exceptionFromErrorImplementation,
          parser,
          limit,
          childError,
          key,
          [newException, ...newExceptions],
          newException,
          newExceptionId,
        );
      }
    });
  }

  return newExceptions;
}

function applyExceptionGroupFieldsForParentException(exception, exceptionId) {
  // Don't know if this default makes sense. The protocol requires us to set these values so we pick *some* default.
  exception.mechanism = exception.mechanism || { type: 'generic', handled: true };

  exception.mechanism = {
    ...exception.mechanism,
    is_exception_group: true,
    exception_id: exceptionId,
  };
}

function applyExceptionGroupFieldsForChildException(
  exception,
  source,
  exceptionId,
  parentId,
) {
  // Don't know if this default makes sense. The protocol requires us to set these values so we pick *some* default.
  exception.mechanism = exception.mechanism || { type: 'generic', handled: true };

  exception.mechanism = {
    ...exception.mechanism,
    type: 'chained',
    source,
    exception_id: exceptionId,
    parent_id: parentId,
  };
}

/**
 * Truncate the message (exception.value) of all exceptions in the event.
 * Because this event processor is ran after `applyClientOptions`,
 * we need to truncate the message of the added exceptions here.
 */
function truncateAggregateExceptions(exceptions, maxValueLength) {
  return exceptions.map(exception => {
    if (exception.value) {
      exception.value = string.truncate(exception.value, maxValueLength);
    }
    return exception;
  });
}

exports.applyAggregateErrorsToEvent = applyAggregateErrorsToEvent;


},{"./is.js":127,"./string.js":143}],99:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const object = require('./object.js');
const stacktrace = require('./stacktrace.js');
const nodeStackTrace = require('./node-stack-trace.js');

/**
 * A node.js watchdog timer
 * @param pollInterval The interval that we expect to get polled at
 * @param anrThreshold The threshold for when we consider ANR
 * @param callback The callback to call for ANR
 * @returns An object with `poll` and `enabled` functions {@link WatchdogReturn}
 */
function watchdogTimer(
  createTimer,
  pollInterval,
  anrThreshold,
  callback,
) {
  const timer = createTimer();
  let triggered = false;
  let enabled = true;

  setInterval(() => {
    const diffMs = timer.getTimeMs();

    if (triggered === false && diffMs > pollInterval + anrThreshold) {
      triggered = true;
      if (enabled) {
        callback();
      }
    }

    if (diffMs < pollInterval + anrThreshold) {
      triggered = false;
    }
  }, 20);

  return {
    poll: () => {
      timer.reset();
    },
    enabled: (state) => {
      enabled = state;
    },
  };
}

// types copied from inspector.d.ts

/**
 * Converts Debugger.CallFrame to Sentry StackFrame
 */
function callFrameToStackFrame(
  frame,
  url,
  getModuleFromFilename,
) {
  const filename = url ? url.replace(/^file:\/\//, '') : undefined;

  // CallFrame row/col are 0 based, whereas StackFrame are 1 based
  const colno = frame.location.columnNumber ? frame.location.columnNumber + 1 : undefined;
  const lineno = frame.location.lineNumber ? frame.location.lineNumber + 1 : undefined;

  return object.dropUndefinedKeys({
    filename,
    module: getModuleFromFilename(filename),
    function: frame.functionName || '?',
    colno,
    lineno,
    in_app: filename ? nodeStackTrace.filenameIsInApp(filename) : undefined,
  });
}

// The only messages we care about

/**
 * Creates a message handler from the v8 debugger protocol and passed stack frames to the callback when paused.
 */
function createDebugPauseMessageHandler(
  sendCommand,
  getModuleFromFilename,
  pausedStackFrames,
) {
  // Collect scriptId -> url map so we can look up the filenames later
  const scripts = new Map();

  return message => {
    if (message.method === 'Debugger.scriptParsed') {
      scripts.set(message.params.scriptId, message.params.url);
    } else if (message.method === 'Debugger.paused') {
      // copy the frames
      const callFrames = [...message.params.callFrames];
      // and resume immediately
      sendCommand('Debugger.resume');
      sendCommand('Debugger.disable');

      const stackFrames = stacktrace.stripSentryFramesAndReverse(
        callFrames.map(frame =>
          callFrameToStackFrame(frame, scripts.get(frame.location.scriptId), getModuleFromFilename),
        ),
      );

      pausedStackFrames(stackFrames);
    }
  };
}

exports.createDebugPauseMessageHandler = createDebugPauseMessageHandler;
exports.watchdogTimer = watchdogTimer;


},{"./node-stack-trace.js":133,"./object.js":136,"./stacktrace.js":142}],100:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const debugBuild = require('./debug-build.js');
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
  if (!dynamicSamplingContext) {
    return undefined;
  }

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
      debugBuild.DEBUG_BUILD &&
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


},{"./debug-build.js":111,"./is.js":127,"./logger.js":129}],101:[function(require,module,exports){
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

  if (!elem) {
    return '<unknown>';
  }

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
  const allowedAttrs = ['aria-label', 'type', 'name', 'title', 'alt'];
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


},{"./is.js":127,"./worldwide.js":152}],102:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _nullishCoalesce = require('./_nullishCoalesce.js');

// https://github.com/alangpierce/sucrase/tree/265887868966917f3b924ce38dfad01fbab1329f

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


},{"./_nullishCoalesce.js":105}],103:[function(require,module,exports){
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


},{}],104:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _asyncOptionalChain = require('./_asyncOptionalChain.js');

// https://github.com/alangpierce/sucrase/tree/265887868966917f3b924ce38dfad01fbab1329f

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


},{"./_asyncOptionalChain.js":103}],105:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// https://github.com/alangpierce/sucrase/tree/265887868966917f3b924ce38dfad01fbab1329f
//
// The MIT License (MIT)
//
// Copyright (c) 2012-2018 various contributors (see AUTHORS)
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

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


},{}],106:[function(require,module,exports){
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


},{}],107:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const _optionalChain = require('./_optionalChain.js');

// https://github.com/alangpierce/sucrase/tree/265887868966917f3b924ce38dfad01fbab1329f

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


},{"./_optionalChain.js":106}],108:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Creates a cache that evicts keys in fifo order
 * @param size {Number}
 */
function makeFifoCache(
  size,
)

 {
  // Maintain a fifo queue of keys, we cannot rely on Object.keys as the browser may not support it.
  let evictionOrder = [];
  let cache = {};

  return {
    add(key, value) {
      while (evictionOrder.length >= size) {
        // shift is O(n) but this is small size and only happens if we are
        // exceeding the cache size so it should be fine.
        const evictCandidate = evictionOrder.shift();

        if (evictCandidate !== undefined) {
          // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
          delete cache[evictCandidate];
        }
      }

      // in case we have a collision, delete the old key.
      if (cache[key]) {
        this.delete(key);
      }

      evictionOrder.push(key);
      cache[key] = value;
    },
    clear() {
      cache = {};
      evictionOrder = [];
    },
    get(key) {
      return cache[key];
    },
    size() {
      return evictionOrder.length;
    },
    // Delete cache key and return true if it existed, false otherwise.
    delete(key) {
      if (!cache[key]) {
        return false;
      }

      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
      delete cache[key];

      for (let i = 0; i < evictionOrder.length; i++) {
        if (evictionOrder[i] === key) {
          evictionOrder.splice(i, 1);
          break;
        }
      }

      return true;
    },
  };
}

exports.makeFifoCache = makeFifoCache;


},{}],109:[function(require,module,exports){
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


},{"./envelope.js":114,"./time.js":146}],110:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * This code was originally copied from the 'cookie` module at v0.5.0 and was simplified for our use case.
 * https://github.com/jshttp/cookie/blob/a0c84147aab6266bdb3996cf4062e93907c0b0fc/index.js
 * It had the following license:
 *
 * (The MIT License)
 *
 * Copyright (c) 2012-2014 Roman Shtylman <shtylman@gmail.com>
 * Copyright (c) 2015 Douglas Christopher Wilson <doug@somethingdoug.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining
 * a copy of this software and associated documentation files (the
 * 'Software'), to deal in the Software without restriction, including
 * without limitation the rights to use, copy, modify, merge, publish,
 * distribute, sublicense, and/or sell copies of the Software, and to
 * permit persons to whom the Software is furnished to do so, subject to
 * the following conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
 * IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
 * CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
 * TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
 * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */

/**
 * Parses a cookie string
 */
function parseCookie(str) {
  const obj = {};
  let index = 0;

  while (index < str.length) {
    const eqIdx = str.indexOf('=', index);

    // no more cookie pairs
    if (eqIdx === -1) {
      break;
    }

    let endIdx = str.indexOf(';', index);

    if (endIdx === -1) {
      endIdx = str.length;
    } else if (endIdx < eqIdx) {
      // backtrack on prior semicolon
      index = str.lastIndexOf(';', eqIdx - 1) + 1;
      continue;
    }

    const key = str.slice(index, eqIdx).trim();

    // only assign once
    if (undefined === obj[key]) {
      let val = str.slice(eqIdx + 1, endIdx).trim();

      // quoted values
      if (val.charCodeAt(0) === 0x22) {
        val = val.slice(1, -1);
      }

      try {
        obj[key] = val.indexOf('%') !== -1 ? decodeURIComponent(val) : val;
      } catch (e) {
        obj[key] = val;
      }
    }

    index = endIdx + 1;
  }

  return obj;
}

exports.parseCookie = parseCookie;


},{}],111:[function(require,module,exports){
arguments[4][21][0].apply(exports,arguments)
},{"dup":21}],112:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const debugBuild = require('./debug-build.js');
const logger = require('./logger.js');

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
 * @returns Dsn as DsnComponents or undefined if @param str is not a valid DSN string
 */
function dsnFromString(str) {
  const match = DSN_REGEX.exec(str);

  if (!match) {
    // This should be logged to the console
    logger.consoleSandbox(() => {
      // eslint-disable-next-line no-console
      console.error(`Invalid Sentry Dsn: ${str}`);
    });
    return undefined;
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
  if (!debugBuild.DEBUG_BUILD) {
    return true;
  }

  const { port, projectId, protocol } = dsn;

  const requiredComponents = ['protocol', 'publicKey', 'host', 'projectId'];
  const hasMissingRequiredComponent = requiredComponents.find(component => {
    if (!dsn[component]) {
      logger.logger.error(`Invalid Sentry Dsn: ${component} missing`);
      return true;
    }
    return false;
  });

  if (hasMissingRequiredComponent) {
    return false;
  }

  if (!projectId.match(/^\d+$/)) {
    logger.logger.error(`Invalid Sentry Dsn: Invalid projectId ${projectId}`);
    return false;
  }

  if (!isValidProtocol(protocol)) {
    logger.logger.error(`Invalid Sentry Dsn: Invalid protocol ${protocol}`);
    return false;
  }

  if (port && isNaN(parseInt(port, 10))) {
    logger.logger.error(`Invalid Sentry Dsn: Invalid port ${port}`);
    return false;
  }

  return true;
}

/**
 * Creates a valid Sentry Dsn object, identifying a Sentry instance and project.
 * @returns a valid DsnComponents object or `undefined` if @param from is an invalid DSN source
 */
function makeDsn(from) {
  const components = typeof from === 'string' ? dsnFromString(from) : dsnFromComponents(from);
  if (!components || !validateDsn(components)) {
    return undefined;
  }
  return components;
}

exports.dsnFromString = dsnFromString;
exports.dsnToString = dsnToString;
exports.makeDsn = makeDsn;


},{"./debug-build.js":111,"./logger.js":129}],113:[function(require,module,exports){
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
 * users. These flags should live in their respective packages, as we identified user tooling (specifically webpack)
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

/**
 * Get source of SDK.
 */
function getSDKSource() {
  // @ts-expect-error "npm" is injected by rollup during build process
  return "npm";
}

exports.getSDKSource = getSDKSource;
exports.isBrowserBundle = isBrowserBundle;


},{}],114:[function(require,module,exports){
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
 *
 * If the callback returns true, the rest of the items will be skipped.
 */
function forEachEnvelopeItem(
  envelope,
  callback,
) {
  const envelopeItems = envelope[1];

  for (const envelopeItem of envelopeItems) {
    const envelopeItemType = envelopeItem[0].type;
    const result = callback(envelopeItem, envelopeItemType);

    if (result) {
      return true;
    }
  }

  return false;
}

/**
 * Returns true if the envelope contains any of the given envelope item types
 */
function envelopeContainsItemType(envelope, types) {
  return forEachEnvelopeItem(envelope, (_, type) => types.includes(type));
}

/**
 * Encode a string to UTF8.
 */
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
  replay_event: 'replay',
  replay_recording: 'replay',
  check_in: 'monitor',
  feedback: 'feedback',
  // TODO: This is a temporary workaround until we have a proper data category for metrics
  statsd: 'unknown',
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
    ...(!!tunnel && dsn$1 && { dsn: dsn.dsnToString(dsn$1) }),
    ...(dynamicSamplingContext && {
      trace: object.dropUndefinedKeys({ ...dynamicSamplingContext }),
    }),
  };
}

exports.addItemToEnvelope = addItemToEnvelope;
exports.createAttachmentEnvelopeItem = createAttachmentEnvelopeItem;
exports.createEnvelope = createEnvelope;
exports.createEventEnvelopeHeaders = createEventEnvelopeHeaders;
exports.envelopeContainsItemType = envelopeContainsItemType;
exports.envelopeItemTypeToDataCategory = envelopeItemTypeToDataCategory;
exports.forEachEnvelopeItem = forEachEnvelopeItem;
exports.getSdkMetadataForEnvelopeHeader = getSdkMetadataForEnvelopeHeader;
exports.parseEnvelope = parseEnvelope;
exports.serializeEnvelope = serializeEnvelope;


},{"./dsn.js":112,"./normalize.js":135,"./object.js":136}],115:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/** An error emitted by Sentry SDKs and related utilities. */
class SentryError extends Error {
  /** Display name of this error instance. */

   constructor( message, logLevel = 'warn') {
    super(message);this.message = message;
    this.name = new.target.prototype.constructor.name;
    // This sets the prototype to be `Error`, not `SentryError`. It's unclear why we do this, but commenting this line
    // out causes various (seemingly totally unrelated) playwright tests consistently time out. FYI, this makes
    // instances of `SentryError` fail `obj instanceof SentryError` checks.
    Object.setPrototypeOf(this, new.target.prototype);
    this.logLevel = logLevel;
  }
}

exports.SentryError = SentryError;


},{}],116:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('./is.js');
const misc = require('./misc.js');
const normalize = require('./normalize.js');
const object = require('./object.js');

/**
 * Extracts stack frames from the error.stack string
 */
function parseStackFrames(stackParser, error) {
  return stackParser(error.stack || '', 1);
}

/**
 * Extracts stack frames from the error and builds a Sentry Exception
 */
function exceptionFromError(stackParser, error) {
  const exception = {
    type: error.name || error.constructor.name,
    value: error.message,
  };

  const frames = parseStackFrames(stackParser, error);
  if (frames.length) {
    exception.stacktrace = { frames };
  }

  return exception;
}

function getMessageForObject(exception) {
  if ('name' in exception && typeof exception.name === 'string') {
    let message = `'${exception.name}' captured as exception`;

    if ('message' in exception && typeof exception.message === 'string') {
      message += ` with message '${exception.message}'`;
    }

    return message;
  } else if ('message' in exception && typeof exception.message === 'string') {
    return exception.message;
  } else {
    // This will allow us to group events based on top-level keys
    // which is much better than creating new group when any key/value change
    return `Object captured as exception with keys: ${object.extractExceptionKeysForMessage(
      exception ,
    )}`;
  }
}

/**
 * Builds and Event from a Exception
 * @hidden
 */
function eventFromUnknownInput(
  getCurrentHub,
  stackParser,
  exception,
  hint,
) {
  let ex = exception;
  const providedMechanism =
    hint && hint.data && (hint.data ).mechanism;
  const mechanism = providedMechanism || {
    handled: true,
    type: 'generic',
  };

  if (!is.isError(exception)) {
    if (is.isPlainObject(exception)) {
      const hub = getCurrentHub();
      const client = hub.getClient();
      const normalizeDepth = client && client.getOptions().normalizeDepth;
      hub.configureScope(scope => {
        scope.setExtra('__serialized__', normalize.normalizeToSize(exception, normalizeDepth));
      });

      const message = getMessageForObject(exception);
      ex = (hint && hint.syntheticException) || new Error(message);
      (ex ).message = message;
    } else {
      // This handles when someone does: `throw "something awesome";`
      // We use synthesized Error here so we can extract a (rough) stack trace.
      ex = (hint && hint.syntheticException) || new Error(exception );
      (ex ).message = exception ;
    }
    mechanism.synthetic = true;
  }

  const event = {
    exception: {
      values: [exceptionFromError(stackParser, ex )],
    },
  };

  misc.addExceptionTypeValue(event, undefined, undefined);
  misc.addExceptionMechanism(event, mechanism);

  return {
    ...event,
    event_id: hint && hint.event_id,
  };
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
  const event = {
    event_id: hint && hint.event_id,
    level,
    message,
  };

  if (attachStacktrace && hint && hint.syntheticException) {
    const frames = parseStackFrames(stackParser, hint.syntheticException);
    if (frames.length) {
      event.exception = {
        values: [
          {
            value: message,
            stacktrace: { frames },
          },
        ],
      };
    }
  }

  return event;
}

exports.eventFromMessage = eventFromMessage;
exports.eventFromUnknownInput = eventFromUnknownInput;
exports.exceptionFromError = exceptionFromError;
exports.parseStackFrames = parseStackFrames;


},{"./is.js":127,"./misc.js":132,"./normalize.js":135,"./object.js":136}],117:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const aggregateErrors = require('./aggregate-errors.js');
const browser = require('./browser.js');
const dsn = require('./dsn.js');
const error = require('./error.js');
const worldwide = require('./worldwide.js');
const index = require('./instrument/index.js');
const is = require('./is.js');
const isBrowser = require('./isBrowser.js');
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
const userIntegrations = require('./userIntegrations.js');
const cache = require('./cache.js');
const eventbuilder = require('./eventbuilder.js');
const anr = require('./anr.js');
const lru = require('./lru.js');
const _asyncNullishCoalesce = require('./buildPolyfills/_asyncNullishCoalesce.js');
const _asyncOptionalChain = require('./buildPolyfills/_asyncOptionalChain.js');
const _asyncOptionalChainDelete = require('./buildPolyfills/_asyncOptionalChainDelete.js');
const _nullishCoalesce = require('./buildPolyfills/_nullishCoalesce.js');
const _optionalChain = require('./buildPolyfills/_optionalChain.js');
const _optionalChainDelete = require('./buildPolyfills/_optionalChainDelete.js');
const console = require('./instrument/console.js');
const dom = require('./instrument/dom.js');
const xhr = require('./instrument/xhr.js');
const fetch = require('./instrument/fetch.js');
const history = require('./instrument/history.js');
const globalError = require('./instrument/globalError.js');
const globalUnhandledRejection = require('./instrument/globalUnhandledRejection.js');
const _handlers = require('./instrument/_handlers.js');
const nodeStackTrace = require('./node-stack-trace.js');
const escapeStringForRegex = require('./vendor/escapeStringForRegex.js');
const supportsHistory = require('./vendor/supportsHistory.js');



exports.applyAggregateErrorsToEvent = aggregateErrors.applyAggregateErrorsToEvent;
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
exports.addInstrumentationHandler = index.addInstrumentationHandler;
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
exports.isVueViewModel = is.isVueViewModel;
exports.isBrowser = isBrowser.isBrowser;
exports.CONSOLE_LEVELS = logger.CONSOLE_LEVELS;
exports.consoleSandbox = logger.consoleSandbox;
exports.logger = logger.logger;
exports.originalConsoleMethods = logger.originalConsoleMethods;
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
exports.DEFAULT_USER_INCLUDES = requestdata.DEFAULT_USER_INCLUDES;
exports.addRequestDataToEvent = requestdata.addRequestDataToEvent;
exports.addRequestDataToTransaction = requestdata.addRequestDataToTransaction;
exports.extractPathForTransaction = requestdata.extractPathForTransaction;
exports.extractRequestData = requestdata.extractRequestData;
exports.winterCGHeadersToDict = requestdata.winterCGHeadersToDict;
exports.winterCGRequestToRequestData = requestdata.winterCGRequestToRequestData;
exports.severityFromString = severity.severityFromString;
exports.severityLevelFromString = severity.severityLevelFromString;
exports.validSeverityLevels = severity.validSeverityLevels;
exports.createStackParser = stacktrace.createStackParser;
exports.getFunctionName = stacktrace.getFunctionName;
exports.nodeStackLineParser = stacktrace.nodeStackLineParser;
exports.stackParserFromStackParserOptions = stacktrace.stackParserFromStackParserOptions;
exports.stripSentryFramesAndReverse = stacktrace.stripSentryFramesAndReverse;
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
exports.generateSentryTraceHeader = tracing.generateSentryTraceHeader;
exports.tracingContextFromHeaders = tracing.tracingContextFromHeaders;
exports.getSDKSource = env.getSDKSource;
exports.isBrowserBundle = env.isBrowserBundle;
exports.addItemToEnvelope = envelope.addItemToEnvelope;
exports.createAttachmentEnvelopeItem = envelope.createAttachmentEnvelopeItem;
exports.createEnvelope = envelope.createEnvelope;
exports.createEventEnvelopeHeaders = envelope.createEventEnvelopeHeaders;
exports.envelopeContainsItemType = envelope.envelopeContainsItemType;
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
exports.getSanitizedUrlString = url.getSanitizedUrlString;
exports.parseUrl = url.parseUrl;
exports.stripUrlQueryAndFragment = url.stripUrlQueryAndFragment;
exports.addOrUpdateIntegration = userIntegrations.addOrUpdateIntegration;
exports.makeFifoCache = cache.makeFifoCache;
exports.eventFromMessage = eventbuilder.eventFromMessage;
exports.eventFromUnknownInput = eventbuilder.eventFromUnknownInput;
exports.exceptionFromError = eventbuilder.exceptionFromError;
exports.parseStackFrames = eventbuilder.parseStackFrames;
exports.createDebugPauseMessageHandler = anr.createDebugPauseMessageHandler;
exports.watchdogTimer = anr.watchdogTimer;
exports.LRUMap = lru.LRUMap;
exports._asyncNullishCoalesce = _asyncNullishCoalesce._asyncNullishCoalesce;
exports._asyncOptionalChain = _asyncOptionalChain._asyncOptionalChain;
exports._asyncOptionalChainDelete = _asyncOptionalChainDelete._asyncOptionalChainDelete;
exports._nullishCoalesce = _nullishCoalesce._nullishCoalesce;
exports._optionalChain = _optionalChain._optionalChain;
exports._optionalChainDelete = _optionalChainDelete._optionalChainDelete;
exports.addConsoleInstrumentationHandler = console.addConsoleInstrumentationHandler;
exports.addClickKeypressInstrumentationHandler = dom.addClickKeypressInstrumentationHandler;
exports.SENTRY_XHR_DATA_KEY = xhr.SENTRY_XHR_DATA_KEY;
exports.addXhrInstrumentationHandler = xhr.addXhrInstrumentationHandler;
exports.addFetchInstrumentationHandler = fetch.addFetchInstrumentationHandler;
exports.addHistoryInstrumentationHandler = history.addHistoryInstrumentationHandler;
exports.addGlobalErrorInstrumentationHandler = globalError.addGlobalErrorInstrumentationHandler;
exports.addGlobalUnhandledRejectionInstrumentationHandler = globalUnhandledRejection.addGlobalUnhandledRejectionInstrumentationHandler;
exports.resetInstrumentationHandlers = _handlers.resetInstrumentationHandlers;
exports.filenameIsInApp = nodeStackTrace.filenameIsInApp;
exports.escapeStringForRegex = escapeStringForRegex.escapeStringForRegex;
exports.supportsHistory = supportsHistory.supportsHistory;


},{"./aggregate-errors.js":98,"./anr.js":99,"./baggage.js":100,"./browser.js":101,"./buildPolyfills/_asyncNullishCoalesce.js":102,"./buildPolyfills/_asyncOptionalChain.js":103,"./buildPolyfills/_asyncOptionalChainDelete.js":104,"./buildPolyfills/_nullishCoalesce.js":105,"./buildPolyfills/_optionalChain.js":106,"./buildPolyfills/_optionalChainDelete.js":107,"./cache.js":108,"./clientreport.js":109,"./dsn.js":112,"./env.js":113,"./envelope.js":114,"./error.js":115,"./eventbuilder.js":116,"./instrument/_handlers.js":118,"./instrument/console.js":119,"./instrument/dom.js":120,"./instrument/fetch.js":121,"./instrument/globalError.js":122,"./instrument/globalUnhandledRejection.js":123,"./instrument/history.js":124,"./instrument/index.js":125,"./instrument/xhr.js":126,"./is.js":127,"./isBrowser.js":128,"./logger.js":129,"./lru.js":130,"./memo.js":131,"./misc.js":132,"./node-stack-trace.js":133,"./node.js":134,"./normalize.js":135,"./object.js":136,"./path.js":137,"./promisebuffer.js":138,"./ratelimit.js":139,"./requestdata.js":140,"./severity.js":141,"./stacktrace.js":142,"./string.js":143,"./supports.js":144,"./syncpromise.js":145,"./time.js":146,"./tracing.js":147,"./url.js":148,"./userIntegrations.js":149,"./vendor/escapeStringForRegex.js":150,"./vendor/supportsHistory.js":151,"./worldwide.js":152}],118:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const debugBuild = require('../debug-build.js');
const logger = require('../logger.js');
const stacktrace = require('../stacktrace.js');

// We keep the handlers globally
const handlers = {};
const instrumented = {};

/** Add a handler function. */
function addHandler(type, handler) {
  handlers[type] = handlers[type] || [];
  (handlers[type] ).push(handler);
}

/**
 * Reset all instrumentation handlers.
 * This can be used by tests to ensure we have a clean slate of instrumentation handlers.
 */
function resetInstrumentationHandlers() {
  Object.keys(handlers).forEach(key => {
    handlers[key ] = undefined;
  });
}

/** Maybe run an instrumentation function, unless it was already called. */
function maybeInstrument(type, instrumentFn) {
  if (!instrumented[type]) {
    instrumentFn();
    instrumented[type] = true;
  }
}

/** Trigger handlers for a given instrumentation type. */
function triggerHandlers(type, data) {
  const typeHandlers = type && handlers[type];
  if (!typeHandlers) {
    return;
  }

  for (const handler of typeHandlers) {
    try {
      handler(data);
    } catch (e) {
      debugBuild.DEBUG_BUILD &&
        logger.logger.error(
          `Error while triggering instrumentation handler.\nType: ${type}\nName: ${stacktrace.getFunctionName(handler)}\nError:`,
          e,
        );
    }
  }
}

exports.addHandler = addHandler;
exports.maybeInstrument = maybeInstrument;
exports.resetInstrumentationHandlers = resetInstrumentationHandlers;
exports.triggerHandlers = triggerHandlers;


},{"../debug-build.js":111,"../logger.js":129,"../stacktrace.js":142}],119:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const logger = require('../logger.js');
const object = require('../object.js');
const worldwide = require('../worldwide.js');
const _handlers = require('./_handlers.js');

/**
 * Add an instrumentation handler for when a console.xxx method is called.
 *
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addConsoleInstrumentationHandler(handler) {
  const type = 'console';
  _handlers.addHandler(type, handler);
  _handlers.maybeInstrument(type, instrumentConsole);
}

function instrumentConsole() {
  if (!('console' in worldwide.GLOBAL_OBJ)) {
    return;
  }

  logger.CONSOLE_LEVELS.forEach(function (level) {
    if (!(level in worldwide.GLOBAL_OBJ.console)) {
      return;
    }

    object.fill(worldwide.GLOBAL_OBJ.console, level, function (originalConsoleMethod) {
      logger.originalConsoleMethods[level] = originalConsoleMethod;

      return function (...args) {
        const handlerData = { args, level };
        _handlers.triggerHandlers('console', handlerData);

        const log = logger.originalConsoleMethods[level];
        log && log.apply(worldwide.GLOBAL_OBJ.console, args);
      };
    });
  });
}

exports.addConsoleInstrumentationHandler = addConsoleInstrumentationHandler;


},{"../logger.js":129,"../object.js":136,"../worldwide.js":152,"./_handlers.js":118}],120:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const misc = require('../misc.js');
const object = require('../object.js');
const worldwide = require('../worldwide.js');
const _handlers = require('./_handlers.js');

const WINDOW = worldwide.GLOBAL_OBJ ;
const DEBOUNCE_DURATION = 1000;

let debounceTimerID;
let lastCapturedEventType;
let lastCapturedEventTargetId;

/**
 * Add an instrumentation handler for when a click or a keypress happens.
 *
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addClickKeypressInstrumentationHandler(handler) {
  const type = 'dom';
  _handlers.addHandler(type, handler);
  _handlers.maybeInstrument(type, instrumentDOM);
}

/** Exported for tests only. */
function instrumentDOM() {
  if (!WINDOW.document) {
    return;
  }

  // Make it so that any click or keypress that is unhandled / bubbled up all the way to the document triggers our dom
  // handlers. (Normally we have only one, which captures a breadcrumb for each click or keypress.) Do this before
  // we instrument `addEventListener` so that we don't end up attaching this handler twice.
  const triggerDOMHandler = _handlers.triggerHandlers.bind(null, 'dom');
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

/**
 * Check whether the event is similar to the last captured one. For example, two click events on the same button.
 */
function isSimilarToLastCapturedEvent(event) {
  // If both events have different type, then user definitely performed two separate actions. e.g. click + keypress.
  if (event.type !== lastCapturedEventType) {
    return false;
  }

  try {
    // If both events have the same type, it's still possible that actions were performed on different targets.
    // e.g. 2 clicks on different buttons.
    if (!event.target || (event.target )._sentryId !== lastCapturedEventTargetId) {
      return false;
    }
  } catch (e) {
    // just accessing `target` property can throw an exception in some rare circumstances
    // see: https://github.com/getsentry/sentry-javascript/issues/838
  }

  // If both events have the same type _and_ same `target` (an element which triggered an event, _not necessarily_
  // to which an event listener was attached), we treat them as the same action, as we want to capture
  // only one breadcrumb. e.g. multiple clicks on the same button, or typing inside a user input box.
  return true;
}

/**
 * Decide whether an event should be captured.
 * @param event event to be captured
 */
function shouldSkipDOMEvent(eventType, target) {
  // We are only interested in filtering `keypress` events for now.
  if (eventType !== 'keypress') {
    return false;
  }

  if (!target || !target.tagName) {
    return true;
  }

  // Only consider keypress events on actual input elements. This will disregard keypresses targeting body
  // e.g.tabbing through elements, hotkeys, etc.
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
    return false;
  }

  return true;
}

/**
 * Wraps addEventListener to capture UI breadcrumbs
 */
function makeDOMEventHandler(
  handler,
  globalListener = false,
) {
  return (event) => {
    // It's possible this handler might trigger multiple times for the same
    // event (e.g. event propagation through node ancestors).
    // Ignore if we've already captured that event.
    if (!event || event['_sentryCaptured']) {
      return;
    }

    const target = getEventTarget(event);

    // We always want to skip _some_ events.
    if (shouldSkipDOMEvent(event.type, target)) {
      return;
    }

    // Mark event as "seen"
    object.addNonEnumerableProperty(event, '_sentryCaptured', true);

    if (target && !target._sentryId) {
      // Add UUID to event target so we can identify if
      object.addNonEnumerableProperty(target, '_sentryId', misc.uuid4());
    }

    const name = event.type === 'keypress' ? 'input' : event.type;

    // If there is no last captured event, it means that we can safely capture the new event and store it for future comparisons.
    // If there is a last captured event, see if the new event is different enough to treat it as a unique one.
    // If that's the case, emit the previous event and store locally the newly-captured DOM event.
    if (!isSimilarToLastCapturedEvent(event)) {
      const handlerData = { event, name, global: globalListener };
      handler(handlerData);
      lastCapturedEventType = event.type;
      lastCapturedEventTargetId = target ? target._sentryId : undefined;
    }

    // Start a new debounce timer that will prevent us from capturing multiple events that should be grouped together.
    clearTimeout(debounceTimerID);
    debounceTimerID = WINDOW.setTimeout(() => {
      lastCapturedEventTargetId = undefined;
      lastCapturedEventType = undefined;
    }, DEBOUNCE_DURATION);
  };
}

function getEventTarget(event) {
  try {
    return event.target ;
  } catch (e) {
    // just accessing `target` property can throw an exception in some rare circumstances
    // see: https://github.com/getsentry/sentry-javascript/issues/838
    return null;
  }
}

exports.addClickKeypressInstrumentationHandler = addClickKeypressInstrumentationHandler;
exports.instrumentDOM = instrumentDOM;


},{"../misc.js":132,"../object.js":136,"../worldwide.js":152,"./_handlers.js":118}],121:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const object = require('../object.js');
const supports = require('../supports.js');
const worldwide = require('../worldwide.js');
const _handlers = require('./_handlers.js');

/**
 * Add an instrumentation handler for when a fetch request happens.
 * The handler function is called once when the request starts and once when it ends,
 * which can be identified by checking if it has an `endTimestamp`.
 *
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addFetchInstrumentationHandler(handler) {
  const type = 'fetch';
  _handlers.addHandler(type, handler);
  _handlers.maybeInstrument(type, instrumentFetch);
}

function instrumentFetch() {
  if (!supports.supportsNativeFetch()) {
    return;
  }

  object.fill(worldwide.GLOBAL_OBJ, 'fetch', function (originalFetch) {
    return function (...args) {
      const { method, url } = parseFetchArgs(args);

      const handlerData = {
        args,
        fetchData: {
          method,
          url,
        },
        startTimestamp: Date.now(),
      };

      _handlers.triggerHandlers('fetch', {
        ...handlerData,
      });

      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      return originalFetch.apply(worldwide.GLOBAL_OBJ, args).then(
        (response) => {
          const finishedHandlerData = {
            ...handlerData,
            endTimestamp: Date.now(),
            response,
          };

          _handlers.triggerHandlers('fetch', finishedHandlerData);
          return response;
        },
        (error) => {
          const erroredHandlerData = {
            ...handlerData,
            endTimestamp: Date.now(),
            error,
          };

          _handlers.triggerHandlers('fetch', erroredHandlerData);
          // NOTE: If you are a Sentry user, and you are seeing this stack frame,
          //       it means the sentry.javascript SDK caught an error invoking your application code.
          //       This is expected behavior and NOT indicative of a bug with sentry.javascript.
          throw error;
        },
      );
    };
  });
}

function hasProp(obj, prop) {
  return !!obj && typeof obj === 'object' && !!(obj )[prop];
}

function getUrlFromResource(resource) {
  if (typeof resource === 'string') {
    return resource;
  }

  if (!resource) {
    return '';
  }

  if (hasProp(resource, 'url')) {
    return resource.url;
  }

  if (resource.toString) {
    return resource.toString();
  }

  return '';
}

/**
 * Parses the fetch arguments to find the used Http method and the url of the request.
 * Exported for tests only.
 */
function parseFetchArgs(fetchArgs) {
  if (fetchArgs.length === 0) {
    return { method: 'GET', url: '' };
  }

  if (fetchArgs.length === 2) {
    const [url, options] = fetchArgs ;

    return {
      url: getUrlFromResource(url),
      method: hasProp(options, 'method') ? String(options.method).toUpperCase() : 'GET',
    };
  }

  const arg = fetchArgs[0];
  return {
    url: getUrlFromResource(arg ),
    method: hasProp(arg, 'method') ? String(arg.method).toUpperCase() : 'GET',
  };
}

exports.addFetchInstrumentationHandler = addFetchInstrumentationHandler;
exports.parseFetchArgs = parseFetchArgs;


},{"../object.js":136,"../supports.js":144,"../worldwide.js":152,"./_handlers.js":118}],122:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const worldwide = require('../worldwide.js');
const _handlers = require('./_handlers.js');

let _oldOnErrorHandler = null;

/**
 * Add an instrumentation handler for when an error is captured by the global error handler.
 *
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addGlobalErrorInstrumentationHandler(handler) {
  const type = 'error';
  _handlers.addHandler(type, handler);
  _handlers.maybeInstrument(type, instrumentError);
}

function instrumentError() {
  _oldOnErrorHandler = worldwide.GLOBAL_OBJ.onerror;

  worldwide.GLOBAL_OBJ.onerror = function (
    msg,
    url,
    line,
    column,
    error,
  ) {
    const handlerData = {
      column,
      error,
      line,
      msg,
      url,
    };
    _handlers.triggerHandlers('error', handlerData);

    if (_oldOnErrorHandler && !_oldOnErrorHandler.__SENTRY_LOADER__) {
      // eslint-disable-next-line prefer-rest-params
      return _oldOnErrorHandler.apply(this, arguments);
    }

    return false;
  };

  worldwide.GLOBAL_OBJ.onerror.__SENTRY_INSTRUMENTED__ = true;
}

exports.addGlobalErrorInstrumentationHandler = addGlobalErrorInstrumentationHandler;


},{"../worldwide.js":152,"./_handlers.js":118}],123:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const worldwide = require('../worldwide.js');
const _handlers = require('./_handlers.js');

let _oldOnUnhandledRejectionHandler = null;

/**
 * Add an instrumentation handler for when an unhandled promise rejection is captured.
 *
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addGlobalUnhandledRejectionInstrumentationHandler(
  handler,
) {
  const type = 'unhandledrejection';
  _handlers.addHandler(type, handler);
  _handlers.maybeInstrument(type, instrumentUnhandledRejection);
}

function instrumentUnhandledRejection() {
  _oldOnUnhandledRejectionHandler = worldwide.GLOBAL_OBJ.onunhandledrejection;

  worldwide.GLOBAL_OBJ.onunhandledrejection = function (e) {
    const handlerData = e;
    _handlers.triggerHandlers('unhandledrejection', handlerData);

    if (_oldOnUnhandledRejectionHandler && !_oldOnUnhandledRejectionHandler.__SENTRY_LOADER__) {
      // eslint-disable-next-line prefer-rest-params
      return _oldOnUnhandledRejectionHandler.apply(this, arguments);
    }

    return true;
  };

  worldwide.GLOBAL_OBJ.onunhandledrejection.__SENTRY_INSTRUMENTED__ = true;
}

exports.addGlobalUnhandledRejectionInstrumentationHandler = addGlobalUnhandledRejectionInstrumentationHandler;


},{"../worldwide.js":152,"./_handlers.js":118}],124:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const object = require('../object.js');
require('../debug-build.js');
require('../logger.js');
const worldwide = require('../worldwide.js');
const supportsHistory = require('../vendor/supportsHistory.js');
const _handlers = require('./_handlers.js');

const WINDOW = worldwide.GLOBAL_OBJ ;

let lastHref;

/**
 * Add an instrumentation handler for when a fetch request happens.
 * The handler function is called once when the request starts and once when it ends,
 * which can be identified by checking if it has an `endTimestamp`.
 *
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addHistoryInstrumentationHandler(handler) {
  const type = 'history';
  _handlers.addHandler(type, handler);
  _handlers.maybeInstrument(type, instrumentHistory);
}

function instrumentHistory() {
  if (!supportsHistory.supportsHistory()) {
    return;
  }

  const oldOnPopState = WINDOW.onpopstate;
  WINDOW.onpopstate = function ( ...args) {
    const to = WINDOW.location.href;
    // keep track of the current URL state, as we always receive only the updated state
    const from = lastHref;
    lastHref = to;
    const handlerData = { from, to };
    _handlers.triggerHandlers('history', handlerData);
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

  function historyReplacementFunction(originalHistoryFunction) {
    return function ( ...args) {
      const url = args.length > 2 ? args[2] : undefined;
      if (url) {
        // coerce to string (this is what pushState does)
        const from = lastHref;
        const to = String(url);
        // keep track of the current URL state, as we always receive only the updated state
        lastHref = to;
        const handlerData = { from, to };
        _handlers.triggerHandlers('history', handlerData);
      }
      return originalHistoryFunction.apply(this, args);
    };
  }

  object.fill(WINDOW.history, 'pushState', historyReplacementFunction);
  object.fill(WINDOW.history, 'replaceState', historyReplacementFunction);
}

exports.addHistoryInstrumentationHandler = addHistoryInstrumentationHandler;


},{"../debug-build.js":111,"../logger.js":129,"../object.js":136,"../vendor/supportsHistory.js":151,"../worldwide.js":152,"./_handlers.js":118}],125:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const debugBuild = require('../debug-build.js');
const logger = require('../logger.js');
const console = require('./console.js');
const dom = require('./dom.js');
const fetch = require('./fetch.js');
const globalError = require('./globalError.js');
const globalUnhandledRejection = require('./globalUnhandledRejection.js');
const history = require('./history.js');
const xhr = require('./xhr.js');

// TODO(v8): Consider moving this file (or at least parts of it) into the browser package. The registered handlers are mostly non-generic and we risk leaking runtime specific code into generic packages.

/**
 * Add handler that will be called when given type of instrumentation triggers.
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 * @deprecated Use the proper function per instrumentation type instead!
 */
function addInstrumentationHandler(type, callback) {
  switch (type) {
    case 'console':
      return console.addConsoleInstrumentationHandler(callback);
    case 'dom':
      return dom.addClickKeypressInstrumentationHandler(callback);
    case 'xhr':
      return xhr.addXhrInstrumentationHandler(callback);
    case 'fetch':
      return fetch.addFetchInstrumentationHandler(callback);
    case 'history':
      return history.addHistoryInstrumentationHandler(callback);
    case 'error':
      return globalError.addGlobalErrorInstrumentationHandler(callback);
    case 'unhandledrejection':
      return globalUnhandledRejection.addGlobalUnhandledRejectionInstrumentationHandler(callback);
    default:
      debugBuild.DEBUG_BUILD && logger.logger.warn('unknown instrumentation type:', type);
  }
}

exports.addConsoleInstrumentationHandler = console.addConsoleInstrumentationHandler;
exports.addClickKeypressInstrumentationHandler = dom.addClickKeypressInstrumentationHandler;
exports.addFetchInstrumentationHandler = fetch.addFetchInstrumentationHandler;
exports.addGlobalErrorInstrumentationHandler = globalError.addGlobalErrorInstrumentationHandler;
exports.addGlobalUnhandledRejectionInstrumentationHandler = globalUnhandledRejection.addGlobalUnhandledRejectionInstrumentationHandler;
exports.addHistoryInstrumentationHandler = history.addHistoryInstrumentationHandler;
exports.SENTRY_XHR_DATA_KEY = xhr.SENTRY_XHR_DATA_KEY;
exports.addXhrInstrumentationHandler = xhr.addXhrInstrumentationHandler;
exports.addInstrumentationHandler = addInstrumentationHandler;


},{"../debug-build.js":111,"../logger.js":129,"./console.js":119,"./dom.js":120,"./fetch.js":121,"./globalError.js":122,"./globalUnhandledRejection.js":123,"./history.js":124,"./xhr.js":126}],126:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const is = require('../is.js');
const object = require('../object.js');
const worldwide = require('../worldwide.js');
const _handlers = require('./_handlers.js');

const WINDOW = worldwide.GLOBAL_OBJ ;

const SENTRY_XHR_DATA_KEY = '__sentry_xhr_v3__';

/**
 * Add an instrumentation handler for when an XHR request happens.
 * The handler function is called once when the request starts and once when it ends,
 * which can be identified by checking if it has an `endTimestamp`.
 *
 * Use at your own risk, this might break without changelog notice, only used internally.
 * @hidden
 */
function addXhrInstrumentationHandler(handler) {
  const type = 'xhr';
  _handlers.addHandler(type, handler);
  _handlers.maybeInstrument(type, instrumentXHR);
}

/** Exported only for tests. */
function instrumentXHR() {
  // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
  if (!(WINDOW ).XMLHttpRequest) {
    return;
  }

  const xhrproto = XMLHttpRequest.prototype;

  object.fill(xhrproto, 'open', function (originalOpen) {
    return function ( ...args) {
      const startTimestamp = Date.now();

      // open() should always be called with two or more arguments
      // But to be on the safe side, we actually validate this and bail out if we don't have a method & url
      const method = is.isString(args[0]) ? args[0].toUpperCase() : undefined;
      const url = parseUrl(args[1]);

      if (!method || !url) {
        return;
      }

      this[SENTRY_XHR_DATA_KEY] = {
        method,
        url,
        request_headers: {},
      };

      // if Sentry key appears in URL, don't capture it as a request
      if (method === 'POST' && url.match(/sentry_key/)) {
        this.__sentry_own_request__ = true;
      }

      const onreadystatechangeHandler = () => {
        // For whatever reason, this is not the same instance here as from the outer method
        const xhrInfo = this[SENTRY_XHR_DATA_KEY];

        if (!xhrInfo) {
          return;
        }

        if (this.readyState === 4) {
          try {
            // touching statusCode in some platforms throws
            // an exception
            xhrInfo.status_code = this.status;
          } catch (e) {
            /* do nothing */
          }

          const handlerData = {
            args: [method, url],
            endTimestamp: Date.now(),
            startTimestamp,
            xhr: this,
          };
          _handlers.triggerHandlers('xhr', handlerData);
        }
      };

      if ('onreadystatechange' in this && typeof this.onreadystatechange === 'function') {
        object.fill(this, 'onreadystatechange', function (original) {
          return function ( ...readyStateArgs) {
            onreadystatechangeHandler();
            return original.apply(this, readyStateArgs);
          };
        });
      } else {
        this.addEventListener('readystatechange', onreadystatechangeHandler);
      }

      // Intercepting `setRequestHeader` to access the request headers of XHR instance.
      // This will only work for user/library defined headers, not for the default/browser-assigned headers.
      // Request cookies are also unavailable for XHR, as `Cookie` header can't be defined by `setRequestHeader`.
      object.fill(this, 'setRequestHeader', function (original) {
        return function ( ...setRequestHeaderArgs) {
          const [header, value] = setRequestHeaderArgs;

          const xhrInfo = this[SENTRY_XHR_DATA_KEY];

          if (xhrInfo && is.isString(header) && is.isString(value)) {
            xhrInfo.request_headers[header.toLowerCase()] = value;
          }

          return original.apply(this, setRequestHeaderArgs);
        };
      });

      return originalOpen.apply(this, args);
    };
  });

  object.fill(xhrproto, 'send', function (originalSend) {
    return function ( ...args) {
      const sentryXhrData = this[SENTRY_XHR_DATA_KEY];

      if (!sentryXhrData) {
        return;
      }

      if (args[0] !== undefined) {
        sentryXhrData.body = args[0];
      }

      const handlerData = {
        args: [sentryXhrData.method, sentryXhrData.url],
        startTimestamp: Date.now(),
        xhr: this,
      };
      _handlers.triggerHandlers('xhr', handlerData);

      return originalSend.apply(this, args);
    };
  });
}

function parseUrl(url) {
  if (is.isString(url)) {
    return url;
  }

  try {
    // url can be a string or URL
    // but since URL is not available in IE11, we do not check for it,
    // but simply assume it is an URL and return `toString()` from it (which returns the full URL)
    // If that fails, we just return undefined
    return (url ).toString();
  } catch (e2) {} // eslint-disable-line no-empty

  return undefined;
}

exports.SENTRY_XHR_DATA_KEY = SENTRY_XHR_DATA_KEY;
exports.addXhrInstrumentationHandler = addXhrInstrumentationHandler;
exports.instrumentXHR = instrumentXHR;


},{"../is.js":127,"../object.js":136,"../worldwide.js":152,"./_handlers.js":118}],127:[function(require,module,exports){
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

/**
 * Checks whether given value's type is a Vue ViewModel.
 *
 * @param wat A value to be checked.
 * @returns A boolean representing the result.
 */
function isVueViewModel(wat) {
  // Not using Object.prototype.toString because in Vue 3 it would read the instance's Symbol(Symbol.toStringTag) property.
  return !!(typeof wat === 'object' && wat !== null && ((wat ).__isVue || (wat )._isVue));
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
exports.isVueViewModel = isVueViewModel;


},{}],128:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const node = require('./node.js');
const worldwide = require('./worldwide.js');

/**
 * Returns true if we are in the browser.
 */
function isBrowser() {
  // eslint-disable-next-line no-restricted-globals
  return typeof window !== 'undefined' && (!node.isNodeEnv() || isElectronNodeRenderer());
}

// Electron renderers with nodeIntegration enabled are detected as Node.js so we specifically test for them
function isElectronNodeRenderer() {
  return (
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-explicit-any
    (worldwide.GLOBAL_OBJ ).process !== undefined && ((worldwide.GLOBAL_OBJ ).process ).type === 'renderer'
  );
}

exports.isBrowser = isBrowser;


},{"./node.js":134,"./worldwide.js":152}],129:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const debugBuild = require('./debug-build.js');
const worldwide = require('./worldwide.js');

/** Prefix for logging strings */
const PREFIX = 'Sentry Logger ';

const CONSOLE_LEVELS = [
  'debug',
  'info',
  'warn',
  'error',
  'log',
  'assert',
  'trace',
] ;

/** This may be mutated by the console instrumentation. */
const originalConsoleMethods

 = {};

/** JSDoc */

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

  const console = worldwide.GLOBAL_OBJ.console ;
  const wrappedFuncs = {};

  const wrappedLevels = Object.keys(originalConsoleMethods) ;

  // Restore all wrapped console methods
  wrappedLevels.forEach(level => {
    const originalConsoleMethod = originalConsoleMethods[level] ;
    wrappedFuncs[level] = console[level] ;
    console[level] = originalConsoleMethod;
  });

  try {
    return callback();
  } finally {
    // Revert restoration to wrapped state
    wrappedLevels.forEach(level => {
      console[level] = wrappedFuncs[level] ;
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
    isEnabled: () => enabled,
  };

  if (debugBuild.DEBUG_BUILD) {
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

const logger = makeLogger();

exports.CONSOLE_LEVELS = CONSOLE_LEVELS;
exports.consoleSandbox = consoleSandbox;
exports.logger = logger;
exports.originalConsoleMethods = originalConsoleMethods;


},{"./debug-build.js":111,"./worldwide.js":152}],130:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/** A simple Least Recently Used map */
class LRUMap {

   constructor(  _maxSize) {this._maxSize = _maxSize;
    this._cache = new Map();
  }

  /** Get the current size of the cache */
   get size() {
    return this._cache.size;
  }

  /** Get an entry or undefined if it was not in the cache. Re-inserts to update the recently used order */
   get(key) {
    const value = this._cache.get(key);
    if (value === undefined) {
      return undefined;
    }
    // Remove and re-insert to update the order
    this._cache.delete(key);
    this._cache.set(key, value);
    return value;
  }

  /** Insert an entry and evict an older entry if we've reached maxSize */
   set(key, value) {
    if (this._cache.size >= this._maxSize) {
      // keys() returns an iterator in insertion order so keys().next() gives us the oldest key
      this._cache.delete(this._cache.keys().next().value);
    }
    this._cache.set(key, value);
  }

  /** Remove an entry and return the entry if it was in the cache */
   remove(key) {
    const value = this._cache.get(key);
    if (value) {
      this._cache.delete(key);
    }
    return value;
  }

  /** Clear all entries */
   clear() {
    this._cache.clear();
  }

  /** Get all the keys */
   keys() {
    return Array.from(this._cache.keys());
  }

  /** Get all the values */
   values() {
    const values = [];
    this._cache.forEach(value => values.push(value));
    return values;
  }
}

exports.LRUMap = LRUMap;


},{}],131:[function(require,module,exports){
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


},{}],132:[function(require,module,exports){
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

  let getRandomByte = () => Math.random() * 16;
  try {
    if (crypto && crypto.randomUUID) {
      return crypto.randomUUID().replace(/-/g, '');
    }
    if (crypto && crypto.getRandomValues) {
      getRandomByte = () => crypto.getRandomValues(new Uint8Array(1))[0];
    }
  } catch (_) {
    // some runtimes can crash invoking crypto
    // https://github.com/getsentry/sentry-javascript/issues/8935
  }

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
  const sourceLine = Math.max(Math.min(maxLines - 1, frame.lineno - 1), 0);

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


},{"./object.js":136,"./string.js":143,"./worldwide.js":152}],133:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Does this filename look like it's part of the app code?
 */
function filenameIsInApp(filename, isNative = false) {
  const isInternal =
    isNative ||
    (filename &&
      // It's not internal if it's an absolute linux path
      !filename.startsWith('/') &&
      // It's not internal if it's an absolute windows path
      !filename.includes(':\\') &&
      // It's not internal if the path is starting with a dot
      !filename.startsWith('.') &&
      // It's not internal if the frame has a protocol. In node, this is usually the case if the file got pre-processed with a bundler like webpack
      !filename.match(/^[a-zA-Z]([a-zA-Z0-9.\-+])*:\/\//)); // Schema from: https://stackoverflow.com/a/3641782

  // in_app is all that's not an internal Node function or a module within node_modules
  // note that isNative appears to return true even for node core libraries
  // see https://github.com/getsentry/raven-node/issues/176

  return !isInternal && filename !== undefined && !filename.includes('node_modules/');
}

/** Node Stack line parser */
// eslint-disable-next-line complexity
function node(getModule) {
  const FILENAME_MATCH = /^\s*[-]{4,}$/;
  const FULL_MATCH = /at (?:async )?(?:(.+?)\s+\()?(?:(.+):(\d+):(\d+)?|([^)]+))\)?/;

  // eslint-disable-next-line complexity
  return (line) => {
    const lineMatch = line.match(FULL_MATCH);

    if (lineMatch) {
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
          object = functionName.slice(0, methodStart);
          method = functionName.slice(methodStart + 1);
          const objectEnd = object.indexOf('.Module');
          if (objectEnd > 0) {
            functionName = functionName.slice(objectEnd + 1);
            object = object.slice(0, objectEnd);
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

      let filename = lineMatch[2] && lineMatch[2].startsWith('file://') ? lineMatch[2].slice(7) : lineMatch[2];
      const isNative = lineMatch[5] === 'native';

      if (!filename && lineMatch[5] && !isNative) {
        filename = lineMatch[5];
      }

      return {
        filename,
        module: getModule ? getModule(filename) : undefined,
        function: functionName,
        lineno: parseInt(lineMatch[3], 10) || undefined,
        colno: parseInt(lineMatch[4], 10) || undefined,
        in_app: filenameIsInApp(filename, isNative),
      };
    }

    if (line.match(FILENAME_MATCH)) {
      return {
        filename: line,
      };
    }

    return undefined;
  };
}

exports.filenameIsInApp = filenameIsInApp;
exports.node = node;


},{}],134:[function(require,module,exports){
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
},{"./env.js":113,"_process":153}],135:[function(require,module,exports){
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
function normalize(input, depth = 100, maxProperties = +Infinity) {
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
  if (
    value == null || // this matches null and undefined -> eqeq not eqeqeq
    (['number', 'boolean', 'string'].includes(typeof value) && !is.isNaN(value))
  ) {
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

  // We can set `__sentry_override_normalization_depth__` on an object to ensure that from there
  // We keep a certain amount of depth.
  // This should be used sparingly, e.g. we use it for the redux integration to ensure we get a certain amount of state.
  const remainingDepth =
    typeof (value )['__sentry_override_normalization_depth__'] === 'number'
      ? ((value )['__sentry_override_normalization_depth__'] )
      : depth;

  // We're also done if we've reached the max depth
  if (remainingDepth === 0) {
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
      return visit('', jsonValue, remainingDepth - 1, maxProperties, memo$1);
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
    normalized[visitKey] = visit(visitKey, visitValue, remainingDepth - 1, maxProperties, memo$1);

    numAdded++;
  }

  // Once we've visited all the branches, remove the parent from memo storage
  unmemoize(value);

  // Return accumulated values
  return normalized;
}

/* eslint-disable complexity */
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

    if (is.isVueViewModel(value)) {
      return '[VueViewModel]';
    }

    // React's SyntheticEvent thingy
    if (is.isSyntheticEvent(value)) {
      return '[SyntheticEvent]';
    }

    if (typeof value === 'number' && value !== value) {
      return '[NaN]';
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
    const objName = getConstructorName(value);

    // Handle HTML Elements
    if (/^HTML(\w*)Element$/.test(objName)) {
      return `[HTMLElement: ${objName}]`;
    }

    return `[object ${objName}]`;
  } catch (err) {
    return `**non-serializable** (${err})`;
  }
}
/* eslint-enable complexity */

function getConstructorName(value) {
  const prototype = Object.getPrototypeOf(value);

  return prototype ? prototype.constructor.name : 'null prototype';
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
},{"./is.js":127,"./memo.js":131,"./object.js":136,"./stacktrace.js":142}],136:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const browser = require('./browser.js');
const debugBuild = require('./debug-build.js');
const is = require('./is.js');
const logger = require('./logger.js');
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
    markFunctionWrapped(wrapped, original);
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
  try {
    Object.defineProperty(obj, name, {
      // enumerable: false, // the default, so we can save on bundle size by not explicitly setting it
      value: value,
      writable: true,
      configurable: true,
    });
  } catch (o_O) {
    debugBuild.DEBUG_BUILD && logger.logger.log(`Failed to add non-enumerable property "${name}" to object`, obj);
  }
}

/**
 * Remembers the original function on the wrapped function and
 * patches up the prototype.
 *
 * @param wrapped the wrapper function
 * @param original the original function that gets wrapped
 */
function markFunctionWrapped(wrapped, original) {
  try {
    const proto = original.prototype || {};
    wrapped.prototype = original.prototype = proto;
    addNonEnumerableProperty(wrapped, '__sentry_original__', original);
  } catch (o_O) {} // eslint-disable-line no-empty
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


},{"./browser.js":101,"./debug-build.js":111,"./is.js":127,"./logger.js":129,"./string.js":143}],137:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// Slightly modified (no IE8 support, ES6) and transcribed to TypeScript
// https://github.com/calvinmetcalf/rollup-plugin-node-builtins/blob/63ab8aacd013767445ca299e468d9a60a95328d7/src/es6/path.js
//
// Copyright Joyent, Inc.and other Node contributors.
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to permit
// persons to whom the Software is furnished to do so, subject to the
// following conditions:
//
// The above copyright notice and this permission notice shall be included
// in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
// NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
// DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
// OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
// USE OR OTHER DEALINGS IN THE SOFTWARE.

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
const splitPathRe = /^(\S+:\\|\/?)([\s\S]*?)((?:\.{1,2}|[^/\\]+?|)(\.[^./\\]*|))(?:[/\\]*)$/;
/** JSDoc */
function splitPath(filename) {
  // Truncate files names greater than 1024 characters to avoid regex dos
  // https://github.com/getsentry/sentry-javascript/pull/8737#discussion_r1285719172
  const truncated = filename.length > 1024 ? `<truncated>${filename.slice(-1024)}` : filename;
  const parts = splitPathRe.exec(truncated);
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
  from = resolve(from).slice(1);
  to = resolve(to).slice(1);
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
  const trailingSlash = path.slice(-1) === '/';

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
    dir = dir.slice(0, dir.length - 1);
  }

  return root + dir;
}

/** JSDoc */
function basename(path, ext) {
  let f = splitPath(path)[2];
  if (ext && f.slice(ext.length * -1) === ext) {
    f = f.slice(0, f.length - ext.length);
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


},{}],138:[function(require,module,exports){
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


},{"./error.js":115,"./syncpromise.js":145}],139:[function(require,module,exports){
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
 * Gets the time that the given category is disabled until for rate limiting.
 * In case no category-specific limit is set but a general rate limit across all categories is active,
 * that time is returned.
 *
 * @return the time in ms that the category is disabled until or 0 if there's no active rate limit.
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
 *
 * @return the updated RateLimits object.
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


},{}],140:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const cookie = require('./cookie.js');
const debugBuild = require('./debug-build.js');
const is = require('./is.js');
const logger = require('./logger.js');
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
      // if exist _reconstructedRoute return that path instead of route.path
      const customRoute = req._reconstructedRoute ? req._reconstructedRoute : undefined;
      return extractPathForTransaction(req, { path: true, method: true, customRoute })[0];
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
  const absoluteUrl = originalUrl.startsWith(protocol) ? originalUrl : `${protocol}://${host}${originalUrl}`;
  include.forEach(key => {
    switch (key) {
      case 'headers': {
        requestData.headers = headers;

        // Remove the Cookie header in case cookie data should not be included in the event
        if (!include.includes('cookies')) {
          delete (requestData.headers ).cookie;
        }

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
        requestData.cookies =
          // TODO (v8 / #5257): We're only sending the empty object for backwards compatibility, so the last bit can
          // come off in v8
          req.cookies || (headers.cookie && cookie.parseCookie(headers.cookie)) || {};
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
 * Add data from the given request to the given event
 *
 * @param event The event to which the request data will be added
 * @param req Request object
 * @param options.include Flags to control what data is included
 * @param options.deps Injected platform-specific dependencies
 * @returns The mutated `Event` object
 */
function addRequestDataToEvent(
  event,
  req,
  options,
) {
  const include = {
    ...DEFAULT_INCLUDES,
    ...(options && options.include),
  };

  if (include.request) {
    const extractedRequestData = Array.isArray(include.request)
      ? extractRequestData(req, { include: include.request, deps: options && options.deps })
      : extractRequestData(req, { deps: options && options.deps });

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

  try {
    return (
      req.query ||
      (typeof URL !== undefined && new URL(originalUrl).search.slice(1)) ||
      // In Node 8, `URL` isn't in the global scope, so we have to use the built-in module from Node
      (deps && deps.url && deps.url.parse(originalUrl).query) ||
      undefined
    );
  } catch (e2) {
    return undefined;
  }
}

/**
 * Transforms a `Headers` object that implements the `Web Fetch API` (https://developer.mozilla.org/en-US/docs/Web/API/Headers) into a simple key-value dict.
 * The header keys will be lower case: e.g. A "Content-Type" header will be stored as "content-type".
 */
function winterCGHeadersToDict(winterCGHeaders) {
  const headers = {};
  try {
    winterCGHeaders.forEach((value, key) => {
      if (typeof value === 'string') {
        // We check that value is a string even though it might be redundant to make sure prototype pollution is not possible.
        headers[key] = value;
      }
    });
  } catch (e) {
    debugBuild.DEBUG_BUILD &&
      logger.logger.warn('Sentry failed extracting headers from a request object. If you see this, please file an issue.');
  }

  return headers;
}

/**
 * Converts a `Request` object that implements the `Web Fetch API` (https://developer.mozilla.org/en-US/docs/Web/API/Headers) into the format that the `RequestData` integration understands.
 */
function winterCGRequestToRequestData(req) {
  const headers = winterCGHeadersToDict(req.headers);
  return {
    method: req.method,
    url: req.url,
    headers,
  };
}

exports.DEFAULT_USER_INCLUDES = DEFAULT_USER_INCLUDES;
exports.addRequestDataToEvent = addRequestDataToEvent;
exports.addRequestDataToTransaction = addRequestDataToTransaction;
exports.extractPathForTransaction = extractPathForTransaction;
exports.extractRequestData = extractRequestData;
exports.winterCGHeadersToDict = winterCGHeadersToDict;
exports.winterCGRequestToRequestData = winterCGRequestToRequestData;


},{"./cookie.js":110,"./debug-build.js":111,"./is.js":127,"./logger.js":129,"./normalize.js":135,"./url.js":148}],141:[function(require,module,exports){
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


},{}],142:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const nodeStackTrace = require('./node-stack-trace.js');

const STACKTRACE_FRAME_LIMIT = 50;
// Used to sanitize webpack (error: *) wrapped stack errors
const WEBPACK_ERROR_REGEXP = /\(error: (.*)\)/;
const STRIP_FRAME_REGEXP = /captureMessage|captureException/;

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
    const lines = stack.split('\n');

    for (let i = skipFirst; i < lines.length; i++) {
      const line = lines[i];
      // Ignore lines over 1kb as they are unlikely to be stack frames.
      // Many of the regular expressions use backtracking which results in run time that increases exponentially with
      // input size. Huge strings can result in hangs/Denial of Service:
      // https://github.com/getsentry/sentry-javascript/issues/2286
      if (line.length > 1024) {
        continue;
      }

      // https://github.com/getsentry/sentry-javascript/issues/5459
      // Remove webpack (error: *) wrappers
      const cleanedLine = WEBPACK_ERROR_REGEXP.test(line) ? line.replace(WEBPACK_ERROR_REGEXP, '$1') : line;

      // https://github.com/getsentry/sentry-javascript/issues/7813
      // Skip Error: lines
      if (cleanedLine.match(/\S*Error: /)) {
        continue;
      }

      for (const parser of sortedParsers) {
        const frame = parser(cleanedLine);

        if (frame) {
          frames.push(frame);
          break;
        }
      }

      if (frames.length >= STACKTRACE_FRAME_LIMIT) {
        break;
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
 * Removes Sentry frames from the top and bottom of the stack if present and enforces a limit of max number of frames.
 * Assumes stack input is ordered from top to bottom and returns the reverse representation so call site of the
 * function that caused the crash is the last frame in the array.
 * @hidden
 */
function stripSentryFramesAndReverse(stack) {
  if (!stack.length) {
    return [];
  }

  const localStack = Array.from(stack);

  // If stack starts with one of our API calls, remove it (starts, meaning it's the top of the stack - aka last call)
  if (/sentryWrapped/.test(localStack[localStack.length - 1].function || '')) {
    localStack.pop();
  }

  // Reversing in the middle of the procedure allows us to just pop the values off the stack
  localStack.reverse();

  // If stack ends with one of our internal API calls, remove it (ends, meaning it's the bottom of the stack - aka top-most call)
  if (STRIP_FRAME_REGEXP.test(localStack[localStack.length - 1].function || '')) {
    localStack.pop();

    // When using synthetic events, we will have a 2 levels deep stack, as `new Error('Sentry syntheticException')`
    // is produced within the hub itself, making it:
    //
    //   Sentry.captureException()
    //   getCurrentHub().captureException()
    //
    // instead of just the top `Sentry` call itself.
    // This forces us to possibly strip an additional frame in the exact same was as above.
    if (STRIP_FRAME_REGEXP.test(localStack[localStack.length - 1].function || '')) {
      localStack.pop();
    }
  }

  return localStack.slice(0, STACKTRACE_FRAME_LIMIT).map(frame => ({
    ...frame,
    filename: frame.filename || localStack[localStack.length - 1].filename,
    function: frame.function || '?',
  }));
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

/**
 * Node.js stack line parser
 *
 * This is in @sentry/utils so it can be used from the Electron SDK in the browser for when `nodeIntegration == true`.
 * This allows it to be used without referencing or importing any node specific code which causes bundlers to complain
 */
function nodeStackLineParser(getModule) {
  return [90, nodeStackTrace.node(getModule)];
}

exports.filenameIsInApp = nodeStackTrace.filenameIsInApp;
exports.createStackParser = createStackParser;
exports.getFunctionName = getFunctionName;
exports.nodeStackLineParser = nodeStackLineParser;
exports.stackParserFromStackParserOptions = stackParserFromStackParserOptions;
exports.stripSentryFramesAndReverse = stripSentryFramesAndReverse;


},{"./node-stack-trace.js":133}],143:[function(require,module,exports){
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
  return str.length <= max ? str : `${str.slice(0, max)}...`;
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
      // This is a hack to fix a Vue3-specific bug that causes an infinite loop of
      // console warnings. This happens when a Vue template is rendered with
      // an undeclared variable, which we try to stringify, ultimately causing
      // Vue to issue another warning which repeats indefinitely.
      // see: https://github.com/getsentry/sentry-javascript/pull/8981
      if (is.isVueViewModel(value)) {
        output.push('[VueViewModel]');
      } else {
        output.push(String(value));
      }
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

exports.isMatchingPattern = isMatchingPattern;
exports.safeJoin = safeJoin;
exports.snipLine = snipLine;
exports.stringMatchesSomePattern = stringMatchesSomePattern;
exports.truncate = truncate;


},{"./is.js":127}],144:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const debugBuild = require('./debug-build.js');
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
    // @ts-expect-error It really needs 1 argument, not 0.
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
  if (typeof EdgeRuntime === 'string') {
    return true;
  }

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
      debugBuild.DEBUG_BUILD &&
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

exports.isNativeFetch = isNativeFetch;
exports.supportsDOMError = supportsDOMError;
exports.supportsDOMException = supportsDOMException;
exports.supportsErrorEvent = supportsErrorEvent;
exports.supportsFetch = supportsFetch;
exports.supportsNativeFetch = supportsNativeFetch;
exports.supportsReferrerPolicy = supportsReferrerPolicy;
exports.supportsReportingObserver = supportsReportingObserver;


},{"./debug-build.js":111,"./logger.js":129,"./worldwide.js":152}],145:[function(require,module,exports){
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

   constructor(
    executor,
  ) {SyncPromise.prototype.__init.call(this);SyncPromise.prototype.__init2.call(this);SyncPromise.prototype.__init3.call(this);SyncPromise.prototype.__init4.call(this);
    this._state = States.PENDING;
    this._handlers = [];

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
    __init() {this._resolve = (value) => {
    this._setResult(States.RESOLVED, value);
  };}

  /** JSDoc */
    __init2() {this._reject = (reason) => {
    this._setResult(States.REJECTED, reason);
  };}

  /** JSDoc */
    __init3() {this._setResult = (state, value) => {
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
    __init4() {this._executeHandlers = () => {
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


},{"./is.js":127}],146:[function(require,module,exports){
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

/**
 * Re-exported with an old name for backwards-compatibility.
 * TODO (v8): Remove this
 *
 * @deprecated Use `timestampInSeconds` instead.
 */
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


},{"./node.js":134,"./worldwide.js":152}],147:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const baggage = require('./baggage.js');
const misc = require('./misc.js');

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
  if (!traceparent) {
    return undefined;
  }

  const matches = traceparent.match(TRACEPARENT_REGEXP);
  if (!matches) {
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

/**
 * Create tracing context from incoming headers.
 */
function tracingContextFromHeaders(
  sentryTrace,
  baggage$1,
)

 {
  const traceparentData = extractTraceparentData(sentryTrace);
  const dynamicSamplingContext = baggage.baggageHeaderToDynamicSamplingContext(baggage$1);

  const { traceId, parentSpanId, parentSampled } = traceparentData || {};

  const propagationContext = {
    traceId: traceId || misc.uuid4(),
    spanId: misc.uuid4().substring(16),
    sampled: parentSampled,
  };

  if (parentSpanId) {
    propagationContext.parentSpanId = parentSpanId;
  }

  if (dynamicSamplingContext) {
    propagationContext.dsc = dynamicSamplingContext ;
  }

  return {
    traceparentData,
    dynamicSamplingContext,
    propagationContext,
  };
}

/**
 * Create sentry-trace header from span context values.
 */
function generateSentryTraceHeader(
  traceId = misc.uuid4(),
  spanId = misc.uuid4().substring(16),
  sampled,
) {
  let sampledString = '';
  if (sampled !== undefined) {
    sampledString = sampled ? '-1' : '-0';
  }
  return `${traceId}-${spanId}${sampledString}`;
}

exports.TRACEPARENT_REGEXP = TRACEPARENT_REGEXP;
exports.extractTraceparentData = extractTraceparentData;
exports.generateSentryTraceHeader = generateSentryTraceHeader;
exports.tracingContextFromHeaders = tracingContextFromHeaders;


},{"./baggage.js":100,"./misc.js":132}],148:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

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
    search: query,
    hash: fragment,
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

/**
 * Takes a URL object and returns a sanitized string which is safe to use as span description
 * see: https://develop.sentry.dev/sdk/data-handling/#structuring-data
 */
function getSanitizedUrlString(url) {
  const { protocol, host, path } = url;

  const filteredHost =
    (host &&
      host
        // Always filter out authority
        .replace(/^.*@/, '[filtered]:[filtered]@')
        // Don't show standard :80 (http) and :443 (https) ports to reduce the noise
        // TODO: Use new URL global if it exists
        .replace(/(:80)$/, '')
        .replace(/(:443)$/, '')) ||
    '';

  return `${protocol ? `${protocol}://` : ''}${filteredHost}${path}`;
}

exports.getNumberOfUrlSegments = getNumberOfUrlSegments;
exports.getSanitizedUrlString = getSanitizedUrlString;
exports.parseUrl = parseUrl;
exports.stripUrlQueryAndFragment = stripUrlQueryAndFragment;


},{}],149:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

/**
 * Recursively traverses an object to update an existing nested key.
 * Note: The provided key path must include existing properties,
 * the function will not create objects while traversing.
 *
 * @param obj An object to update
 * @param value The value to update the nested key with
 * @param keyPath The path to the key to update ex. fizz.buzz.foo
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function setNestedKey(obj, keyPath, value) {
  // Ex. foo.bar.zoop will extract foo and bar.zoop
  const match = keyPath.match(/([a-z_]+)\.(.*)/i);
  // The match will be null when there's no more recursing to do, i.e., when we've reached the right level of the object
  if (match === null) {
    obj[keyPath] = value;
  } else {
    // `match[1]` is the initial segment of the path, and `match[2]` is the remainder of the path
    const innerObj = obj[match[1]];
    setNestedKey(innerObj, match[2], value);
  }
}

/**
 * Enforces inclusion of a given integration with specified options in an integration array originally determined by the
 * user, by either including the given default instance or by patching an existing user instance with the given options.
 *
 * Ideally this would happen when integrations are set up, but there isn't currently a mechanism there for merging
 * options from a default integration instance with those from a user-provided instance of the same integration, only
 * for allowing the user to override a default instance entirely. (TODO: Fix that.)
 *
 * @param defaultIntegrationInstance An instance of the integration with the correct options already set
 * @param userIntegrations Integrations defined by the user.
 * @param forcedOptions Options with which to patch an existing user-derived instance on the integration.
 * @returns A final integrations array.
 */
function addOrUpdateIntegration(
  defaultIntegrationInstance,
  userIntegrations,
  forcedOptions = {},
) {
  return (
    Array.isArray(userIntegrations)
      ? addOrUpdateIntegrationInArray(defaultIntegrationInstance, userIntegrations, forcedOptions)
      : addOrUpdateIntegrationInFunction(
          defaultIntegrationInstance,
          // Somehow TS can't figure out that not being an array makes this necessarily a function
          userIntegrations ,
          forcedOptions,
        )
  ) ;
}

function addOrUpdateIntegrationInArray(
  defaultIntegrationInstance,
  userIntegrations,
  forcedOptions,
) {
  const userInstance = userIntegrations.find(integration => integration.name === defaultIntegrationInstance.name);

  if (userInstance) {
    for (const [keyPath, value] of Object.entries(forcedOptions)) {
      setNestedKey(userInstance, keyPath, value);
    }

    return userIntegrations;
  }

  return [...userIntegrations, defaultIntegrationInstance];
}

function addOrUpdateIntegrationInFunction(
  defaultIntegrationInstance,
  userIntegrationsFunc,
  forcedOptions,
) {
  const wrapper = defaultIntegrations => {
    const userFinalIntegrations = userIntegrationsFunc(defaultIntegrations);

    // There are instances where we want the user to be able to prevent an integration from appearing at all, which they
    // would do by providing a function which filters out the integration in question. If that's happened in one of
    // those cases, don't add our default back in.
    if (defaultIntegrationInstance.allowExclusionByUser) {
      const userFinalInstance = userFinalIntegrations.find(
        integration => integration.name === defaultIntegrationInstance.name,
      );
      if (!userFinalInstance) {
        return userFinalIntegrations;
      }
    }

    return addOrUpdateIntegrationInArray(defaultIntegrationInstance, userFinalIntegrations, forcedOptions);
  };

  return wrapper;
}

exports.addOrUpdateIntegration = addOrUpdateIntegration;


},{}],150:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

// Based on https://github.com/sindresorhus/escape-string-regexp but with modifications to:
//   a) reduce the size by skipping the runtime type - checking
//   b) ensure it gets down - compiled for old versions of Node(the published package only supports Node 12+).
//
// MIT License
//
// Copyright (c) Sindre Sorhus <sindresorhus@gmail.com> (https://sindresorhus.com)
//
// Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
// documentation files(the "Software"), to deal in the Software without restriction, including without limitation
// the rights to use, copy, modify, merge, publish, distribute, sublicense, and / or sell copies of the Software, and
// to permit persons to whom the Software is furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all copies or substantial portions of
// the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
// THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
// TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
// IN THE SOFTWARE.

/**
 * Given a string, escape characters which have meaning in the regex grammar, such that the result is safe to feed to
 * `new RegExp()`.
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


},{}],151:[function(require,module,exports){
Object.defineProperty(exports, '__esModule', { value: true });

const worldwide = require('../worldwide.js');

// Based on https://github.com/angular/angular.js/pull/13945/files

// eslint-disable-next-line deprecation/deprecation
const WINDOW = worldwide.getGlobalObject();

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

exports.supportsHistory = supportsHistory;


},{"../worldwide.js":152}],152:[function(require,module,exports){
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
},{}],153:[function(require,module,exports){
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

},{}]},{},[38])(38)
});
