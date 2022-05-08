// import $ from "./vendor/jquery.js";
import Tribute from "./vendor/tribute.js";

console.log(Tribute);

/* Username autocompletion */
var tribute = new Tribute({
  trigger: "@",
  requireLeadingSpace: true,
  menuShowMinLength: 2,
  searchOpts: {
    pre: "​",
    post: "​",
  },
  noMatchTemplate: function () {
    return "";
  },
  menuItemTemplate: function (item) {
    let link = document.createElement("a");
    link.innerText = item.string;
    return link.outerHTML;
  },
  values: (text, callback) => {
    $.ajax({
      type: "GET",
      url: `/api/users/?username=${text}`,
      dataType: "json",
      success: function (data) {
        var userMentionList = data.results.map(function (user) {
          return {
            value: user.username,
            key: `${user.full_name} (${user.username})`,
          };
        });
        callback(userMentionList);
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error(errorThrown);
      },
    });
  },
});
export default function attachTributeTo(elements) {
  tribute.attach(elements);
  elements.forEach((editor) => {
    editor.addEventListener("tribute-active-true", function (e) {
      $(".tribute-container").addClass("open");
      $(".tribute-container ul").addClass("dropdown-menu");
    });
  });
}
