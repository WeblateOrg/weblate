# Weblate OpenShift

## Provisioning

To upload the weblate template to your current project’s template library, pass the `template.yml` file with the following command:

```bash
# oc create -f <FILENAME> | <URL>
oc create -f template.yml
```

The template is now available for selection using the web console or the CLI.

You can also use the CLI to process templates and use the configuration that is generated to create objects immediately.

```bash
# oc process -f <FILENAME> | <URL>
oc process -f https://raw.githubusercontent.com/WeblateOrg/weblate/master/openshift3/template.yml | oc create -f -
```

## Deprovisioning

```bash
oc delete all -l app=<APPLICATION_NAME>
oc delete configmap -l app= <APPLICATION_NAME>
oc delete secret -l app=<APPLICATION_NAME>
# ATTTENTION! The following command is only optional and will permanently delete all of your data.
oc delete pvc -l app=<APPLICATION_NAME>

oc delete all -l app=weblate && oc delete secret -l app=weblate && oc delete configmap -l app=weblate && oc delete pvc -l app=weblate
```
