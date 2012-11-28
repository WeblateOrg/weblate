/*
 * jQuery outerHTML
 *
 * Copyright (c) 2008 Ca-Phun Ung <caphun at yelotofu dot com>
 * Dual licensed under the MIT (MIT-LICENSE.txt)
 * and GPL (GPL-LICENSE.txt) licenses.
 *
 * http://yelotofu.com/labs/jquery/snippets/outerhtml/
 *
 * outerHTML is based on the outerHTML work done by Brandon Aaron
 * But adds the ability to replace an element.
 */

(function($) {
	$.fn.outerHTML = function(s) {
		return (s) 
			? this.before(s).remove() 
			: $('<p>').append(this.eq(0).clone()).html();
	}
})(jQuery);
