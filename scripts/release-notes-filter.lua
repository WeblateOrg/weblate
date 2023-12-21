-- Copyright © Michal Čihař <michal@weblate.org>
--
-- SPDX-License-Identifier: GPL-3.0-or-later

function fix_link (url)
  return url:sub(1,4) == "http" and url or "https://docs.weblate.org/en/latest/" .. url
end
function Link (link)
  link.target = fix_link(link.target);
  return link
end
function Image (img)
  img.src = fix_link(img.src);
  return src
end
return {{Link = Link, Image = Image}}
