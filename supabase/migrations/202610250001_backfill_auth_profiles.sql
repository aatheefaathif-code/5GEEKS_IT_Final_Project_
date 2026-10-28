create table if not exists public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    role text not null default 'parent' check (role in ('parent', 'teacher')),
    full_name text not null default 'Parent',
    created_at timestamptz not null default now()
);

create or replace function public.create_parent_profile()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    insert into public.profiles (user_id, role)
    values (new.id, 'parent')
    on conflict (user_id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created_profile on auth.users;
create trigger on_auth_user_created_profile
after insert on auth.users
for each row execute procedure public.create_parent_profile();

create table if not exists public.students (
    id uuid primary key default gen_random_uuid(),
    display_name text not null check (length(trim(display_name)) between 1 and 80),
    grade smallint not null check (grade between 1 and 5),
    parent_user_id uuid not null references public.profiles(user_id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (id, parent_user_id)
);

create table if not exists public.teacher_student_access (
    teacher_user_id uuid not null references public.profiles(user_id) on delete cascade,
    student_id uuid not null references public.students(id) on delete cascade,
    approved_by_parent_user_id uuid not null references public.profiles(user_id),
    approved_at timestamptz not null default now(),
    foreign key (student_id, approved_by_parent_user_id)
        references public.students(id, parent_user_id) on delete cascade,
    primary key (teacher_user_id, student_id)
);

create table if not exists public.textbook_quizzes (
    id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.students(id) on delete cascade,
    grade smallint not null check (grade between 1 and 5),
    subject text not null,
    topic text not null,
    medium text not null check (medium in ('English', 'Sinhala', 'Tamil')),
    questions jsonb not null check (jsonb_typeof(questions) = 'array'),
    source_chunk_ids text[] not null check (cardinality(source_chunk_ids) > 0),
    created_at timestamptz not null default now()
);

create table if not exists public.quiz_attempts (
    id uuid primary key default gen_random_uuid(),
    quiz_id uuid not null unique references public.textbook_quizzes(id) on delete cascade,
    student_id uuid not null references public.students(id) on delete cascade,
    score smallint not null check (score >= 0),
    total smallint not null check (total between 3 and 5),
    answers smallint[] not null,
    created_at timestamptz not null default now(),
    check (score <= total),
    check (cardinality(answers) = total)
);

create table if not exists public.badge_awards (
    id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.students(id) on delete cascade,
    badge_code text not null check (
        badge_code in ('first_quiz', 'careful_thinker', 'steady_learner')
    ),
    awarded_at timestamptz not null default now(),
    unique (student_id, badge_code)
);

create or replace function public.award_quiz_badges()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    perform pg_advisory_xact_lock(hashtextextended(new.student_id::text, 0));

    insert into public.badge_awards (student_id, badge_code)
    values (new.student_id, 'first_quiz')
    on conflict (student_id, badge_code) do nothing;

    if new.score * 100 >= new.total * 80 then
        insert into public.badge_awards (student_id, badge_code)
        values (new.student_id, 'careful_thinker')
        on conflict (student_id, badge_code) do nothing;
    end if;

    if (
        select count(*)
        from public.quiz_attempts qa
        where qa.student_id = new.student_id
    ) >= 3 then
        insert into public.badge_awards (student_id, badge_code)
        values (new.student_id, 'steady_learner')
        on conflict (student_id, badge_code) do nothing;
    end if;
    return new;
end;
$$;

drop trigger if exists award_badges_after_quiz_attempt on public.quiz_attempts;
create trigger award_badges_after_quiz_attempt
after insert on public.quiz_attempts
for each row execute procedure public.award_quiz_badges();

create index if not exists students_parent_user_id_idx
    on public.students (parent_user_id);
create index if not exists teacher_student_access_student_id_idx
    on public.teacher_student_access (student_id);
create index if not exists textbook_quizzes_student_created_idx
    on public.textbook_quizzes (student_id, created_at desc);
create index if not exists quiz_attempts_student_created_idx
    on public.quiz_attempts (student_id, created_at desc);
create index if not exists badge_awards_student_id_idx
    on public.badge_awards (student_id);

create or replace view public.student_progress_summary
with (security_invoker = true)
as
select
    student_id,
    count(*)::integer as completed_quizzes,
    coalesce(sum(score), 0)::integer as correct_answers,
    coalesce(sum(total), 0)::integer as answered_questions
from public.quiz_attempts
group by student_id;

create or replace function public.can_access_student(target_student_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (
        select 1
        from public.students s
        where s.id = target_student_id
          and s.parent_user_id = auth.uid()
    ) or exists (
        select 1
        from public.teacher_student_access tsa
        join public.profiles p on p.user_id = tsa.teacher_user_id
        where tsa.student_id = target_student_id
          and tsa.teacher_user_id = auth.uid()
          and p.role = 'teacher'
    );
$$;

alter table public.profiles enable row level security;
alter table public.students enable row level security;
alter table public.teacher_student_access enable row level security;
alter table public.textbook_quizzes enable row level security;
alter table public.quiz_attempts enable row level security;
alter table public.badge_awards enable row level security;

drop policy if exists "users read own profile" on public.profiles;
create policy "users read own profile"
    on public.profiles for select to authenticated
    using (user_id = auth.uid());

drop policy if exists "parents and authorized teachers read students" on public.students;
create policy "parents and authorized teachers read students"
    on public.students for select to authenticated
    using (public.can_access_student(id));

drop policy if exists "parents create their own student records" on public.students;
create policy "parents create their own student records"
    on public.students for insert to authenticated
    with check (
        parent_user_id = auth.uid()
        and exists (
            select 1 from public.profiles p
            where p.user_id = auth.uid() and p.role = 'parent'
        )
    );

drop policy if exists "parents update their own student records" on public.students;
create policy "parents update their own student records"
    on public.students for update to authenticated
    using (
        parent_user_id = auth.uid()
        and exists (
            select 1 from public.profiles p
            where p.user_id = auth.uid() and p.role = 'parent'
        )
    )
    with check (
        parent_user_id = auth.uid()
        and exists (
            select 1 from public.profiles p
            where p.user_id = auth.uid() and p.role = 'parent'
        )
    );

drop policy if exists "authorized users read teacher links" on public.teacher_student_access;
create policy "authorized users read teacher links"
    on public.teacher_student_access for select to authenticated
    using (
        teacher_user_id = auth.uid()
        or approved_by_parent_user_id = auth.uid()
    );

drop policy if exists "authorized users read textbook quizzes" on public.textbook_quizzes;
create policy "authorized users read textbook quizzes"
    on public.textbook_quizzes for select to authenticated
    using (public.can_access_student(student_id));

drop policy if exists "authorized users read quiz attempts" on public.quiz_attempts;
create policy "authorized users read quiz attempts"
    on public.quiz_attempts for select to authenticated
    using (public.can_access_student(student_id));

drop policy if exists "authorized users read badge awards" on public.badge_awards;
create policy "authorized users read badge awards"
    on public.badge_awards for select to authenticated
    using (public.can_access_student(student_id));

revoke all on function public.can_access_student(uuid) from public;
grant execute on function public.can_access_student(uuid) to authenticated;
grant select on public.profiles to authenticated;
grant select, insert, update on public.students to authenticated;
grant select on public.teacher_student_access to authenticated;
grant select on public.textbook_quizzes to authenticated;
grant select on public.quiz_attempts to authenticated;
grant select on public.badge_awards to authenticated;
grant select on public.student_progress_summary to authenticated;
