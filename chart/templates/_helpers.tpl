{{/*
Expand the name of the chart.
*/}}
{{- define "harness-agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully qualified app name. Honours fullnameOverride; otherwise composes
{release}-{chart} truncated to 63 chars per DNS label rules.
*/}}
{{- define "harness-agent.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels stamped on every resource.
*/}}
{{- define "harness-agent.labels" -}}
app.kubernetes.io/name: {{ include "harness-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{/*
Selector labels used by Deployment + Service to bind to the Pods.
*/}}
{{- define "harness-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "harness-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Service account name resolver — emits "default" when serviceAccount
.create is false and no explicit name is configured.
*/}}
{{- define "harness-agent.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "harness-agent.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
