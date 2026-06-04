INSERT INTO roles (code, title) VALUES
    ('admin', 'Администратор'),
    ('student', 'Студент'),
    ('teacher', 'Преподаватель')
ON CONFLICT (code) DO NOTHING;

INSERT INTO content.faq (question, answer, source_url)
SELECT v.question, v.answer, v.source_url
FROM (VALUES
    (
        'Как поступить в ВятГУ?',
        'Подробные правила приема, сроки и перечень документов смотрите на официальной странице приемной кампании.',
        'https://www.vyatsu.ru/abitur/'
    ),
    (
        'Где найти расписание занятий?',
        'Расписание и учебные сервисы доступны в личном кабинете и в разделах для обучающихся на официальном сайте.',
        'https://www.vyatsu.ru/studentu-1/'
    ),
    (
        'Где посмотреть адреса и телефоны учебных корпусов?',
        'Актуальный список корпусов, адресов и телефонов размещен на официальной странице университета.',
        'https://www.vyatsu.ru/studentu-1/pervokursniku/adresa-i-telefonyi-uchebnyih-korpusov-fakul-tetov.html'
    ),
    (
        'Где посмотреть информацию об общежитиях?',
        'Информация по общежитиям, адресам и контактам доступна на официальной странице ВятГУ.',
        'https://www.vyatsu.ru/studentu-1/obschezhitiya-3/obschezhitiya-vyatgu.html'
    ),
    (
        'Куда обращаться по вопросам обучения и сервисов студента?',
        'Контакты подразделений и общие каналы связи опубликованы на странице контактов ВятГУ.',
        'https://www.vyatsu.ru/kontaktyi.html'
    ),
    (
        'Где смотреть официальные новости университета?',
        'Официальные новости и объявления публикуются на сайте ВятГУ в разделе новостей.',
        'https://www.vyatsu.ru/internet-gazeta/'
    )
) AS v(question, answer, source_url)
WHERE NOT EXISTS (
    SELECT 1 FROM content.faq f WHERE f.question = v.question
);
