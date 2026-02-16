# Copyright © Boost Orgnaization <boost@boost.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from weblate.boost_endpoint.serializers import AddOrUpdateRequestSerializer
from weblate.boost_endpoint.services import BoostComponentService


class BoostEndpointInfo(APIView):
    """Boost documentation translation API info."""

    permission_classes = (IsAuthenticated,)

    def get(self, request, format=None):
        """Return Boost endpoint module info."""
        return Response({
            "module": "boost-endpoint",
            "description": "Boost documentation translation API",
        })


class AddOrUpdateView(APIView):
    """Add or update Boost documentation components."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, format=None):
        """
        Create or update Boost documentation components.

        For each submodule:
        1. Clone the repository
        2. Scan for supported documentation files
        3. Create or update project
        4. Create or update components
        5. Add language translations
        """
        serializer = AddOrUpdateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        organization = data["organization"]
        submodules = data["submodules"]
        lang_code = data["lang_code"]
        version = data["version"]
        extensions = data.get("extensions")

        # Create service instance
        service = BoostComponentService(
            organization=organization,
            lang_code=lang_code,
            version=version,
            extensions=extensions,
        )

        # Process all submodules (pass request so do_update and add_new_language work)
        results = service.process_all(
            submodules, user=request.user, request=request
        )

        return Response(results, status=status.HTTP_200_OK)
