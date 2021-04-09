$(function () {
  $("#support-form").ZammadForm({
    messageTitle: gettext("Weblate feedback"),
    messageSubmit: gettext("Get help"),
    messageThankYou: gettext(
      "Thank you for your inquiry (#%s)! We'll contact you as soon as possible."
    ),
    showTitle: true,
    modal: true,
    attachmentSupport: true,
    attributes: [
      {
        display: gettext("Subject"),
        name: "title",
        tag: "input",
        type: "text",
        placeholder: "",
        defaultValue: "Weblate feedback [" + window.location.hostname + "]",
      },
      {
        display: gettext("Your name"),
        name: "name",
        tag: "input",
        type: "text",
        placeholder: "",
        defaultValue: $("#support-form").data("fullname"),
      },
      {
        display: gettext("Your e-mail"),
        name: "email",
        tag: "input",
        type: "email",
        placeholder: "",
        defaultValue: $("#support-form").data("email"),
      },
      {
        display: gettext("Message"),
        name: "body",
        tag: "textarea",
        placeholder: gettext(
          "Please contact us in English, otherwise we might be unable to process your request."
        ),
        defaultValue: "",
        rows: 7,
      },
      {
        display: gettext("Attachments"),
        name: "file[]",
        tag: "input",
        type: "file",
        repeat: 3,
      },
    ],
  });
});
