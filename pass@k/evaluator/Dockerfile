FROM alpine:3.22 AS compiler
RUN apk add --no-cache build-base

FROM compiler AS grader
COPY critter.c evaluator/tests/test_critter.c /src/
RUN cc -std=c11 -O2 -Wall -Wextra -Werror -I /src -c /src/test_critter.c -o /judge.o

FROM compiler
COPY --from=grader /judge.o /judge.o
COPY evaluator/grade.sh /grade.sh
ENTRYPOINT ["/bin/sh", "/grade.sh"]
