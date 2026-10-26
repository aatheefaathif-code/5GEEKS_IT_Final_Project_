insert into public.profiles (user_id, role)
select users.id, 'parent'
from auth.users as users
left join public.profiles as profiles on profiles.user_id = users.id
where profiles.user_id is null
on conflict (user_id) do nothing;
