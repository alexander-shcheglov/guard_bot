FROM postgres:14.5-alpine
ARG LANGUAGE_CODE
ARG TIME_ZONE
RUN apk add --no-cache --update musl musl-utils musl-locales tzdata
ENV LANG $LANGUAGE_CODE.utf8
ENV TZ $TIME_ZONE
ENV LC_ALL $LANGUAGE_CODE.utf8
