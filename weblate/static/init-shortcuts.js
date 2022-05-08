import $ from "./vendor/jquery.js";
import Mousetrap from "./vendor/mousetrap.js";
import "./vendor/mousetrap-global-bind.js";

function submitForm(evt) {
  var $target = $(evt.target);
  var $form = $target.closest("form");

  if ($form.length === 0) {
    $form = $(".translation-form");
  }
  if ($form.length > 0) {
    let submits = $form.find('input[type="submit"]');

    if (submits.length === 0) {
      submits = $form.find('button[type="submit"]');
    }
    if (submits.length > 0) {
      submits[0].click();
    }
  }
  return false;
}
Mousetrap.bindGlobal(["alt+enter", "mod+enter"], submitForm);
