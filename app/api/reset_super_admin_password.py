import asyncio
import getpass
import selectors
import sys

from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import func, select

from core.auth import UserManager
from core.database import async_session_maker
from db.models import Role, User


async def reset_super_admin_password():
    print("=== Super Admin Password Reset ===")
    
    try:
        email_or_username = input("Enter Super Admin email or username: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(0)
        
    if not email_or_username:
        print("Error: Input cannot be empty.")
        sys.exit(1)
    
    async with async_session_maker() as session:
        # Try to find the user case-insensitively
        query = select(User).where(
            (func.lower(User.email) == email_or_username.lower()) | 
            (func.lower(User.username) == email_or_username.lower())
        )
        result = await session.execute(query)
        user = result.scalars().first()
        
        if not user:
            print(f"Error: User '{email_or_username}' not found.")
            sys.exit(1)
            
        # Verify if the user is a super admin
        if not user.role_id:
            print("Error: User does not have a role assigned.")
            sys.exit(1)
            
        role = await session.get(Role, user.role_id)
        if not role or role.role_name != "SUPER_ADMIN":
            print(f"Error: User '{email_or_username}' is not a Super Admin (current role: {role.role_name if role else 'None'}).")
            sys.exit(1)
            
        print(f"Found Super Admin account: {user.email}")
        
        # We need a user manager instance to validate the password
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)
        
        while True:
            try:
                new_password = getpass.getpass("Enter new password: ")
                confirm_password = getpass.getpass("Confirm new password: ")
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                sys.exit(0)
            
            if not new_password:
                print("Error: Password cannot be empty.")
                continue
                
            if new_password != confirm_password:
                print("Passwords do not match. Please try again.")
                continue
                
            try:
                # This will run our custom strict password validation
                await user_manager.validate_password(new_password, user)
                break
            except Exception as e:
                print(f"Invalid password: {e}")
                print("Password Rules: Min 12 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char, no username/email.")
                continue
                
        # Hash the new password and save it
        hashed_password = user_manager.password_helper.hash(new_password)
        
        user.hashed_password = hashed_password
        
        try:
            await session.commit()
            print("Password successfully reset! You can now log in.")
        except Exception as e:
            await session.rollback()
            print(f"An error occurred while saving the password: {e}")
            sys.exit(1)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(
            reset_super_admin_password(), 
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
        )
    else:
        asyncio.run(reset_super_admin_password())
