import { Link } from "@tanstack/react-router";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { OverviewState } from "@/features/overview/overview-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

const steps = [
  {
    title: "1. Выберите проект",
    body: "Проект — это один локальный репозиторий. На экране «Задачи» видно все репозитории с Beads; в Workspace проект нужно зарегистрировать один раз, выбрав его путь из списка.",
  },
  {
    title: "2. Заведите эпик",
    body: "Эпик — крупная работа, вокруг которой идёт переписка с исполнителем. Есть три входа: задача в Beads, issue на GitHub или просто ваша идея.",
  },
  {
    title: "3. Договоритесь о работе",
    body: "Внутри эпика вкладка «Обсуждение» — это переписка с Codex или Claude. Здесь вы формулируете задачу, задаёте вопросы и получаете ответы. Спецификацию и план можно зарегистрировать как файлы репозитория.",
  },
  {
    title: "4. Разложите на задачи",
    body: "Задачи живут в Beads, а не в панели. Заведите их через `bd create` под эпиком — доска эпика покажет их сама.",
  },
  {
    title: "5. Запустите исполнителя",
    body: "Кнопка запуска открывает форму: какая задача, какой рантайм, какая зона записи. Панель запускает Codex или Claude и пишет всё, что они отвечают, в ленту эпика.",
  },
  {
    title: "6. Проверьте и закройте",
    body: "Вкладка Runs показывает запуски и раунды ревью, «Артефакты» — что появилось в репозитории. Готовую задачу закройте на доске: панель отдаёт переход в `bd`, а не меняет статус у себя.",
  },
] as const;

const entries = [
  {
    title: "Из задачи Beads",
    body: "Экран «Задачи» → кнопка «В Workspace» на карточке. Если эпик с этой задачей уже есть, откроется он; если нет — форма создания придёт заполненной.",
  },
  {
    title: "Из GitHub issue",
    body: "Workspace → выберите проект → «Из GitHub issue». Панель читает открытые issue через `gh` и создаёт эпик со ссылкой на источник.",
  },
  {
    title: "Из головы",
    body: "Workspace → «Создать эпик». Название обязательно, задача Beads — по желанию; без неё доска эпика будет пустой.",
  },
] as const;

const ownership = [
  {
    title: "Задачи (Beads)",
    body: "Beads остаётся единственным трекером: статусы, зависимости, приоритеты.",
    items: [
      "Ready — задача без блокеров.",
      "In progress — уже назначенная работа.",
      "Панель только читает Beads и переносит карточки командой `bd`.",
    ],
  },
  {
    title: "Код и документы (Git)",
    body: "Спецификации, планы, доказательства — файлы репозитория.",
    items: [
      "Панель регистрирует путь и контрольную сумму, а не хранит копию.",
      "Коммиты и ветки остаются за вами и агентом.",
    ],
  },
  {
    title: "Чего панель не делает",
    body: "Границы намеренные, чтобы не появилось второго источника правды.",
    items: [
      "Не создаёт задачи в Beads и не меняет issue на GitHub.",
      "Не запускает модель сама: только по вашему явному действию.",
      "Не хранит переписку рантайма: контекст остаётся в его сессии.",
    ],
  },
] as const;

export function HelpScreen() {
  const screen = screenById("help");
  return (
    <ScreenFrame screen={screen} marker={{ kind: "native", id: screen.id }}>
      <OverviewState>
        {(data) => (
          <div className="space-y-6">
            <section aria-labelledby="help-flow" className="space-y-3">
              <h2 className="text-lg font-semibold" id="help-flow">
                Как идёт работа
              </h2>
              <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {steps.map((step) => (
                  <li
                    className="rounded-xl border border-border-soft bg-surface-low p-4"
                    key={step.title}
                  >
                    <p className="font-semibold">{step.title}</p>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {step.body}
                    </p>
                  </li>
                ))}
              </ol>
              <p className="text-sm text-muted-foreground">
                Начать можно отсюда:{" "}
                <Link className="text-primary underline" to="/workspace">
                  Workspace
                </Link>{" "}
                или{" "}
                <Link className="text-primary underline" to="/beads">
                  Задачи
                </Link>
                .
              </p>
            </section>

            <section aria-labelledby="help-entries" className="space-y-3">
              <h2 className="text-lg font-semibold" id="help-entries">
                Три входа в эпик
              </h2>
              <div className="grid gap-3 md:grid-cols-3">
                {entries.map((entry) => (
                  <Card className="bg-card/80" key={entry.title}>
                    <CardHeader className="p-4 pb-2">
                      <CardTitle className="text-base">{entry.title}</CardTitle>
                    </CardHeader>
                    <CardContent className="p-4 pt-0 text-sm leading-6 text-muted-foreground">
                      {entry.body}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </section>

            <section aria-labelledby="help-ownership" className="space-y-3">
              <h2 className="text-lg font-semibold" id="help-ownership">
                Кто чем владеет
              </h2>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {ownership.map((card) => (
                  <Card className="bg-card/80" key={card.title}>
                    <CardHeader className="p-4 pb-2">
                      <CardTitle className="text-base">{card.title}</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 p-4 pt-0 text-sm leading-6 text-muted-foreground">
                      <p>{card.body}</p>
                      <ul className="space-y-2 border-l border-border pl-4">
                        {card.items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </section>

            <section aria-labelledby="help-paths" className="space-y-3">
              <h2 className="text-lg font-semibold" id="help-paths">
                Где что лежит
              </h2>
              <dl className="grid gap-2 rounded-xl border border-border-soft bg-surface-low p-4 font-mono text-xs">
                {[
                  ["Codex home", data.paths.codex_home],
                  ["Workspace", data.paths.workspace],
                  ["Manifest", data.paths.prompt_manifest],
                  ["State", data.paths.state_dir],
                ].map(([label, value]) => (
                  <div
                    className="grid gap-1 sm:grid-cols-[10rem_1fr]"
                    key={label}
                  >
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="break-all">{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-sm text-muted-foreground">
                Локальные данные и секреты не принадлежат Git: state, логи и
                скриншоты не коммитятся, а web, scripts, prompts и документация
                — коммитятся.
              </p>
            </section>
          </div>
        )}
      </OverviewState>
    </ScreenFrame>
  );
}
