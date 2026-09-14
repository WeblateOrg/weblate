// Copyright © Michal Čihař <michal@weblate.org>
// SPDX-License-Identifier: GPL-3.0-or-later
package org.weblate.arsctest;

import android.content.Context;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.content.res.loader.ResourcesLoader;
import android.content.res.loader.ResourcesProvider;
import android.os.ParcelFileDescriptor;
import android.test.InstrumentationTestCase;
import android.text.Spanned;
import android.text.style.StyleSpan;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.Collections;
import java.util.Locale;

public class ResourcesTest extends InstrumentationTestCase {
    private ResourcesProvider provider(String name) throws Exception {
        File file = new File(getInstrumentation().getTargetContext().getCacheDir(), name);
        try (InputStream input = getInstrumentation().getContext().getAssets().open(name);
             FileOutputStream output = new FileOutputStream(file)) {
            byte[] buffer = new byte[8192];
            int length;
            while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
        }
        try (ParcelFileDescriptor fd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)) {
            return ResourcesProvider.loadFromTable(fd, null);
        }
    }

    public void testOverridesAndFallback() throws Exception {
        Context context = getInstrumentation().getTargetContext();
        Configuration configuration = new Configuration(context.getResources().getConfiguration());
        configuration.setLocale(Locale.FRANCE);
        Resources resources = context.createConfigurationContext(configuration).getResources();
        assertEquals(0x7f090003, R.string.welcome);
        assertEquals(0x7f090004, R.string.fallback);
        assertEquals(0x7f080012, R.plurals.count);
        assertEquals("Bundled welcome", resources.getString(R.string.welcome));
        assertEquals("Bundled fallback", resources.getString(R.string.fallback));
        assertEquals("Bundled many", resources.getQuantityString(R.plurals.count, 3));
        ResourcesLoader loader = new ResourcesLoader();
        ResourcesProvider first = provider("fr.arsc");
        ResourcesProvider second = provider("fr-updated.arsc");
        try {
            getInstrumentation().runOnMainSync(() -> {
                loader.addProvider(first);
                resources.addLoaders(loader);
            });
            assertEquals(" Bonjour  😀  ", resources.getString(0x7f090003));
            assertEquals("Bundled fallback", resources.getString(0x7f090004));
            assertEquals("Un\u00a0objet", resources.getQuantityString(0x7f080012, 1));
            assertEquals(" Plusieurs  articles  ", resources.getQuantityString(0x7f080012, 3));
            Spanned styled = (Spanned) resources.getText(0x7f090003);
            StyleSpan[] spans = styled.getSpans(0, styled.length(), StyleSpan.class);
            assertEquals(1, spans.length);
            assertEquals(9, styled.getSpanStart(spans[0]));
            assertEquals(13, styled.getSpanEnd(spans[0]));
            getInstrumentation().runOnMainSync(() -> loader.setProviders(Collections.singletonList(second)));
            assertEquals("Salut", resources.getString(0x7f090003));
            assertEquals("Bundled many", resources.getQuantityString(0x7f080012, 3));
            configuration.setLocale(Locale.GERMANY);
            Resources german = context.createConfigurationContext(configuration).getResources();
            getInstrumentation().runOnMainSync(() -> german.addLoaders(loader));
            try {
                assertEquals("Bundled welcome", german.getString(0x7f090003));
            } finally {
                getInstrumentation().runOnMainSync(() -> german.removeLoaders(loader));
            }
        } finally {
            getInstrumentation().runOnMainSync(() -> {
                resources.removeLoaders(loader);
                loader.clearProviders();
            });
            first.close();
            second.close();
        }
        assertEquals("Bundled welcome", resources.getString(0x7f090003));
    }
}
